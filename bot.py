"""Bot de Telegram que avisa de los nuevos anuncios del Tablón oficial de la URJC."""

from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden
from telegram.ext import Application, CommandHandler, ContextTypes

from storage import Storage
from tablon import Anuncio, Detalle, Tablon

load_dotenv()

TOKEN = os.environ["TELEGRAM_TOKEN"]
INTERVALO_MIN = int(os.getenv("INTERVALO_MIN", "5"))
DB_PATH = os.getenv("DB_PATH", "data/tablon.db")
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Madrid"))
# Si se define, solo estos chat_id pueden usar el bot (separados por comas).
PERMITIDOS = {int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x}

MAX_MSG = 4000  # Telegram corta en 4096 caracteres

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("tablon-bot")

storage = Storage(DB_PATH)
tablon = Tablon()

AYUDA = (
    "📋 <b>Tablón oficial URJC</b>\n\n"
    "Te aviso cada vez que se publique un anuncio nuevo.\n\n"
    "/hoy – anuncios publicados hoy\n"
    "/ayer – anuncios de ayer\n"
    "/fecha dd/mm/aaaa – anuncios de un día concreto\n"
    "/ultimos [n] – los últimos n anuncios (10 por defecto)\n"
    "/buscar texto – busca por título\n"
    "/start – activar avisos\n"
    "/stop – desactivar avisos\n"
    "/ayuda – este mensaje"
)


# --- formato ---------------------------------------------------------------

def linea(a: Anuncio, con_fecha: bool = False) -> str:
    hora = a.inicio.strftime("%d/%m %H:%M" if con_fecha else "%H:%M") if a.inicio else ""
    return f"• <a href=\"{html.escape(a.url)}\">{html.escape(a.titulo)}</a>" + (f" <i>({hora})</i>" if hora else "")


def mensaje_nuevo(a: Anuncio, d: Detalle | None) -> str:
    partes = [f"🆕 <b>{html.escape(a.titulo)}</b>"]
    if d and d.categorias:
        partes.append("🏷 " + ", ".join(html.escape(c) for c in d.categorias))
    if d and d.emisor:
        partes.append("🏛 " + html.escape(d.emisor))
    if a.inicio:
        partes.append("📅 " + a.inicio.strftime("%d/%m/%Y %H:%M"))
    if d and d.anexos:
        partes.append("📎 " + " · ".join(f"<a href=\"{html.escape(u)}\">{html.escape(n)}</a>" for n, u in d.anexos))
    partes.append(f"\n🔗 {html.escape(a.url)}")
    return "\n".join(partes)


def trocear(cabecera: str, lineas: list[str]) -> list[str]:
    """Agrupa líneas en mensajes que no superen el límite de Telegram."""
    mensajes, actual = [], cabecera
    for ln in lineas:
        if len(actual) + len(ln) + 1 > MAX_MSG:
            mensajes.append(actual)
            actual = ""
        actual += ("\n" if actual else "") + ln
    mensajes.append(actual)
    return mensajes


async def responder_lista(update: Update, cabecera: str, anuncios: list[Anuncio], con_fecha: bool = True) -> None:
    if not anuncios:
        await update.effective_message.reply_text(cabecera + "\n\nNo hay anuncios.", parse_mode=ParseMode.HTML)
        return
    for texto in trocear(f"{cabecera} ({len(anuncios)})\n", [linea(a, con_fecha) for a in anuncios]):
        await update.effective_message.reply_text(texto, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# --- control de acceso -----------------------------------------------------

def permitido(update: Update) -> bool:
    return not PERMITIDOS or update.effective_chat.id in PERMITIDOS


def solo_permitidos(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not permitido(update):
            await update.effective_message.reply_text(
                f"⛔ No tienes acceso a este bot. Tu chat_id es {update.effective_chat.id}."
            )
            return
        await func(update, context)

    return wrapper


# --- comandos --------------------------------------------------------------

@solo_permitidos
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    nuevo = storage.suscribir(update.effective_chat.id)
    estado = "✅ Avisos activados." if nuevo else "✅ Ya tenías los avisos activados."
    await update.effective_message.reply_text(f"{estado}\n\n{AYUDA}", parse_mode=ParseMode.HTML)


@solo_permitidos
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage.desuscribir(update.effective_chat.id)
    await update.effective_message.reply_text("🔕 Avisos desactivados. Usa /start para volver a activarlos.")


@solo_permitidos
async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(AYUDA, parse_mode=ParseMode.HTML)


async def _dia(update: Update, dia, titulo: str) -> None:
    anuncios = await tablon.del_dia(dia)
    await responder_lista(update, f"📅 <b>{titulo} – {dia.strftime('%d/%m/%Y')}</b>", anuncios, con_fecha=False)


@solo_permitidos
async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _dia(update, datetime.now(TZ).date(), "Hoy")


@solo_permitidos
async def cmd_ayer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _dia(update, datetime.now(TZ).date() - timedelta(days=1), "Ayer")


@solo_permitidos
async def cmd_fecha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        dia = datetime.strptime(context.args[0], "%d/%m/%Y").date()
    except (IndexError, ValueError):
        await update.effective_message.reply_text("Uso: /fecha dd/mm/aaaa  (ej. /fecha 22/09/2026)")
        return
    await _dia(update, dia, "Anuncios")


@solo_permitidos
async def cmd_ultimos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        n = max(1, min(int(context.args[0]), 50)) if context.args else 10
    except ValueError:
        n = 10
    await responder_lista(update, "🗂 <b>Últimos anuncios</b>", await tablon.recientes(n))


@solo_permitidos
async def cmd_buscar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = " ".join(context.args).strip()
    if not texto:
        await update.effective_message.reply_text("Uso: /buscar texto  (ej. /buscar erasmus)")
        return
    anuncios = await tablon.buscar(max_paginas=2, limite=20, titulo=texto)
    await responder_lista(update, f"🔎 <b>«{html.escape(texto)}»</b>", anuncios)


# --- comprobación periódica ------------------------------------------------

async def comprobar(context: ContextTypes.DEFAULT_TYPE) -> None:
    # Recorre páginas hasta encontrar alguno ya visto (máx. 5).
    nuevos: list[Anuncio] = []
    for page in range(1, 6):
        anuncios, hay_siguiente = await tablon.pagina(page)
        ids_nuevos = set(storage.filtrar_nuevos([a.id for a in anuncios]))
        nuevos += [a for a in anuncios if a.id in ids_nuevos]
        if len(ids_nuevos) < len(anuncios) or not hay_siguiente:
            break

    if not nuevos:
        return

    if not storage.hay_vistos():
        # Primera ejecución: guardar el estado actual sin avisar de todo el histórico.
        storage.marcar_vistos([a.id for a in nuevos])
        log.info("Inicializados %d anuncios como vistos", len(nuevos))
        return

    log.info("%d anuncio(s) nuevo(s)", len(nuevos))
    for a in reversed(nuevos):  # del más antiguo al más reciente
        try:
            detalle = await tablon.detalle(a)
        except Exception:
            log.warning("No se pudo leer el detalle de %s", a.url, exc_info=True)
            detalle = None
        texto = mensaje_nuevo(a, detalle)
        for chat_id in storage.suscriptores():
            try:
                await context.bot.send_message(chat_id, texto, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Forbidden:
                log.info("El chat %s bloqueó el bot; se desuscribe", chat_id)
                storage.desuscribir(chat_id)
            except Exception:
                log.exception("Error enviando a %s", chat_id)
        storage.marcar_vistos([a.id])


async def comprobar_seguro(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await comprobar(context)
    except Exception:
        log.exception("Error comprobando el tablón")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Error en un comando", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ No he podido consultar el tablón. Inténtalo en un rato.")


# --- arranque --------------------------------------------------------------

async def post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("hoy", "Anuncios de hoy"),
            BotCommand("ayer", "Anuncios de ayer"),
            BotCommand("fecha", "Anuncios de un día (dd/mm/aaaa)"),
            BotCommand("ultimos", "Últimos anuncios"),
            BotCommand("buscar", "Buscar por título"),
            BotCommand("start", "Activar avisos"),
            BotCommand("stop", "Desactivar avisos"),
            BotCommand("ayuda", "Ayuda"),
        ]
    )


async def post_shutdown(app: Application) -> None:
    await tablon.close()


def main() -> None:
    app = Application.builder().token(TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    for nombre, fn in {
        "start": cmd_start,
        "stop": cmd_stop,
        "ayuda": cmd_ayuda,
        "help": cmd_ayuda,
        "hoy": cmd_hoy,
        "ayer": cmd_ayer,
        "fecha": cmd_fecha,
        "ultimos": cmd_ultimos,
        "buscar": cmd_buscar,
    }.items():
        app.add_handler(CommandHandler(nombre, fn))
    app.add_error_handler(error_handler)
    app.job_queue.run_repeating(comprobar_seguro, interval=INTERVALO_MIN * 60, first=5)
    log.info("Bot arrancado; comprobando cada %d min", INTERVALO_MIN)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
