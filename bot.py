"""Envía por Telegram un resumen con los anuncios nuevos del Tablón oficial de la URJC.

Pensado para ejecutarse una vez al día (GitHub Actions). Los IDs ya enviados se guardan en
estado.json, así que cada ejecución manda todo lo publicado desde la anterior.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from tablon import Anuncio, Tablon

load_dotenv()

TOKEN = os.environ["TELEGRAM_TOKEN"]
# Chats que reciben el resumen (separados por comas).
CHAT_IDS = [x for x in os.environ["TELEGRAM_CHAT_ID"].replace(" ", "").split(",") if x]
ESTADO_PATH = Path(os.getenv("ESTADO_PATH", "estado.json"))

MAX_MSG = 3800  # Telegram admite 4096 caracteres; se deja margen para la cabecera
MAX_TITULO = 800  # por si algún título es desmesurado
MAX_PAGINAS = 50  # 10 anuncios por página → hasta 500 anuncios por ejecución
MAX_VISTOS = 3000  # IDs recordados; los anuncios tienen IDs crecientes
PAUSA_ENVIO = 1.5  # segundos entre mensajes (Telegram limita ~1 msg/s por chat)
REINTENTOS = 5

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("tablon-bot")


# --- estado ----------------------------------------------------------------

def cargar_vistos() -> set[int]:
    if ESTADO_PATH.exists():
        return set(json.loads(ESTADO_PATH.read_text())["vistos"])
    return set()


def guardar_vistos(vistos: set[int]) -> None:
    ESTADO_PATH.write_text(json.dumps({"vistos": sorted(vistos)[-MAX_VISTOS:]}, indent=1) + "\n")


# --- formato ---------------------------------------------------------------

def linea(a: Anuncio) -> str:
    titulo = a.titulo if len(a.titulo) <= MAX_TITULO else a.titulo[: MAX_TITULO - 1] + "…"
    fecha = f" <i>({a.inicio.strftime('%d/%m %H:%M')})</i>" if a.inicio else ""
    return f"• <a href=\"{html.escape(a.url)}\">{html.escape(titulo)}</a>{fecha}"


def componer_resumen(nuevos: list[Anuncio], truncado: bool) -> list[tuple[str, list[int]]]:
    """Reparte los anuncios en mensajes que caben en Telegram.

    Devuelve (texto, ids incluidos) por mensaje, para ir guardando el progreso.
    """
    bloques: list[tuple[list[str], list[int]]] = [([], [])]
    tam = 0
    for a in nuevos:
        ln = linea(a)
        if bloques[-1][0] and tam + len(ln) + 2 > MAX_MSG:
            bloques.append(([], []))
            tam = 0
        bloques[-1][0].append(ln)
        bloques[-1][1].append(a.id)
        tam += len(ln) + 2

    total = len(bloques)
    mensajes = []
    for i, (lineas, ids) in enumerate(bloques, 1):
        cabecera = f"📋 <b>Tablón URJC – {len(nuevos)} anuncio(s) nuevo(s)</b>"
        if total > 1:
            cabecera += f" ({i}/{total})"
        texto = cabecera + "\n\n" + "\n\n".join(lineas)
        if truncado and i == total:
            texto += (
                f"\n\n⚠️ Solo se muestran los {len(nuevos)} más recientes. "
                "El resto, en https://sede.urjc.es/tablon-oficial"
            )
        mensajes.append((texto, ids))
    return mensajes


# --- telegram --------------------------------------------------------------

async def enviar(client: httpx.AsyncClient, texto: str) -> None:
    for chat_id in CHAT_IDS:
        for intento in range(1, REINTENTOS + 1):
            resp = await client.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": texto,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code == 200:
                break
            if resp.status_code == 429 or resp.status_code >= 500:
                # Demasiados mensajes seguidos: Telegram indica cuánto esperar.
                espera = resp.json().get("parameters", {}).get("retry_after", 5) if resp.status_code == 429 else 5
                log.warning("Telegram respondió %s; reintento %d en %ss", resp.status_code, intento, espera)
                await asyncio.sleep(espera + 1)
                continue
            raise RuntimeError(f"Telegram respondió {resp.status_code}: {resp.text}")
        else:
            raise RuntimeError(f"Telegram sigue rechazando el mensaje tras {REINTENTOS} intentos")
        await asyncio.sleep(PAUSA_ENVIO)


# --- principal -------------------------------------------------------------

async def anuncios_nuevos(tablon: Tablon, vistos: set[int]) -> tuple[list[Anuncio], bool]:
    """Recorre el tablón (del más reciente hacia atrás) hasta dar con uno ya visto.

    Devuelve los nuevos y si se ha cortado por llegar a MAX_PAGINAS.
    """
    nuevos: list[Anuncio] = []
    for page in range(1, MAX_PAGINAS + 1):
        anuncios, hay_siguiente = await tablon.pagina(page)
        pagina_nuevos = [a for a in anuncios if a.id not in vistos]
        nuevos += pagina_nuevos
        if len(pagina_nuevos) < len(anuncios) or not hay_siguiente:
            return nuevos, False
    return nuevos, True


async def main() -> None:
    vistos = cargar_vistos()
    tablon = Tablon()
    try:
        nuevos, truncado = await anuncios_nuevos(tablon, vistos)
    finally:
        await tablon.close()

    async with httpx.AsyncClient(timeout=30) as client:
        if not vistos:
            # Primera ejecución: no mandar todo el histórico, solo confirmar que funciona.
            await enviar(client, "✅ <b>Bot del Tablón URJC configurado.</b>\n"
                                 "A partir de ahora recibirás cada día los anuncios nuevos.")
            guardar_vistos({a.id for a in nuevos})
            log.info("Primera ejecución: %d anuncios marcados como vistos", len(nuevos))
            return
        if not nuevos:
            log.info("No hay anuncios nuevos")
            return

        log.info("%d anuncio(s) nuevo(s)%s", len(nuevos), " (limitado)" if truncado else "")
        nuevos.sort(key=lambda a: a.id)  # del más antiguo al más reciente
        for texto, ids in componer_resumen(nuevos, truncado):
            await enviar(client, texto)
            # Se guarda tras cada mensaje: si algo falla, mañana solo se reenvía lo pendiente.
            vistos |= set(ids)
            guardar_vistos(vistos)


if __name__ == "__main__":
    asyncio.run(main())
