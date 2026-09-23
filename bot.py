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

MAX_MSG = 4000  # Telegram corta en 4096 caracteres
MAX_PAGINAS = 30  # 10 anuncios por página
MAX_VISTOS = 2000  # IDs recordados; los anuncios tienen IDs crecientes

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
    fecha = f" <i>({a.inicio.strftime('%d/%m %H:%M')})</i>" if a.inicio else ""
    return f"• <a href=\"{html.escape(a.url)}\">{html.escape(a.titulo)}</a>{fecha}"


def trocear(cabecera: str, lineas: list[str]) -> list[str]:
    """Agrupa líneas en mensajes que no superen el límite de Telegram."""
    mensajes, actual = [], cabecera
    for ln in lineas:
        if len(actual) + len(ln) + 2 > MAX_MSG:
            mensajes.append(actual)
            actual = ""
        actual += ("\n\n" if actual else "") + ln
    mensajes.append(actual)
    return mensajes


# --- telegram --------------------------------------------------------------

async def enviar(client: httpx.AsyncClient, texto: str) -> None:
    for chat_id in CHAT_IDS:
        resp = await client.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Telegram respondió {resp.status_code}: {resp.text}")


# --- principal -------------------------------------------------------------

async def anuncios_nuevos(tablon: Tablon, vistos: set[int]) -> list[Anuncio]:
    """Recorre el tablón (del más reciente hacia atrás) hasta dar con uno ya visto."""
    nuevos: list[Anuncio] = []
    for page in range(1, MAX_PAGINAS + 1):
        anuncios, hay_siguiente = await tablon.pagina(page)
        pagina_nuevos = [a for a in anuncios if a.id not in vistos]
        nuevos += pagina_nuevos
        if len(pagina_nuevos) < len(anuncios) or not hay_siguiente:
            break
    return nuevos


async def main() -> None:
    vistos = cargar_vistos()
    tablon = Tablon()
    try:
        nuevos = await anuncios_nuevos(tablon, vistos)
    finally:
        await tablon.close()

    async with httpx.AsyncClient(timeout=30) as client:
        if not vistos:
            # Primera ejecución: no mandar todo el histórico, solo confirmar que funciona.
            await enviar(client, "✅ <b>Bot del Tablón URJC configurado.</b>\n"
                                 "A partir de ahora recibirás cada día los anuncios nuevos.")
            log.info("Primera ejecución: %d anuncios marcados como vistos", len(nuevos))
        elif not nuevos:
            log.info("No hay anuncios nuevos")
        else:
            log.info("%d anuncio(s) nuevo(s)", len(nuevos))
            nuevos.sort(key=lambda a: a.id)  # del más antiguo al más reciente
            cabecera = f"📋 <b>Tablón URJC – {len(nuevos)} anuncio(s) nuevo(s)</b>"
            for texto in trocear(cabecera, [linea(a) for a in nuevos]):
                await enviar(client, texto)

    guardar_vistos(vistos | {a.id for a in nuevos})


if __name__ == "__main__":
    asyncio.run(main())
