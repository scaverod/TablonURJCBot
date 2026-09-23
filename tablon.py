"""Scraper del Tablón electrónico oficial de la URJC (https://sede.urjc.es/tablon-oficial)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://sede.urjc.es"
TABLON_URL = f"{BASE_URL}/tablon-oficial"
HEADERS = {"User-Agent": "Mozilla/5.0 (TablonURJC Telegram bot)"}
DATE_FMT = "%d/%m/%Y %H:%M:%S"

@dataclass(frozen=True)
class Anuncio:
    id: int
    titulo: str
    descripcion: str
    url: str
    inicio: datetime | None
    fin: datetime | None


def _parse_fecha(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto.strip(), DATE_FMT)
    except ValueError:
        return None


def _limpia(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def parse_pagina(html: str) -> tuple[list[Anuncio], bool]:
    """Devuelve los anuncios de una página y si existe página siguiente."""
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table", id="result_list")
    anuncios: list[Anuncio] = []
    if tabla is not None:
        for fila in tabla.select("tbody tr"):
            celdas = fila.find_all("td")
            enlace = fila.find("a", href=re.compile(r"/tablon-oficial/anuncio/\d+"))
            if len(celdas) < 4 or enlace is None:
                continue
            href = enlace["href"]
            anuncios.append(
                Anuncio(
                    id=int(re.search(r"/anuncio/(\d+)", href).group(1)),
                    titulo=_limpia(enlace.get_text()),
                    descripcion=_limpia(celdas[1].get_text()),
                    url=urljoin(BASE_URL, href),
                    inicio=_parse_fecha(celdas[2].get_text()),
                    fin=_parse_fecha(celdas[3].get_text()),
                )
            )
    hay_siguiente = soup.select_one("ul.pagination a.next") is not None
    return anuncios, hay_siguiente


class Tablon:
    def __init__(self, timeout: float = 30.0):
        self._client = httpx.AsyncClient(headers=HEADERS, timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def pagina(self, page: int = 1) -> tuple[list[Anuncio], bool]:
        # Sin path=buscar/ la web devuelve la tabla vacía.
        params = {
            "page": page,
            "title": "",
            "description": "",
            "categories": "",
            "fecha_ini": "",
            "fecha_fin": "",
            "path": "buscar/",
        }
        resp = await self._client.get(TABLON_URL, params=params)
        resp.raise_for_status()
        return parse_pagina(resp.text)
