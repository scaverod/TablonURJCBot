"""Scraper del Tablón electrónico oficial de la URJC (https://sede.urjc.es/tablon-oficial)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
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


@dataclass(frozen=True)
class Detalle:
    categorias: list[str]
    emisor: str
    anexos: list[tuple[str, str]]  # (nombre, url)


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


def parse_detalle(html: str) -> Detalle:
    soup = BeautifulSoup(html, "html.parser")
    campos: dict[str, object] = {}
    for li in soup.select("ul.list-group li.list-group-item"):
        etiqueta = li.find("strong")
        if etiqueta is None:
            continue
        clave = _limpia(etiqueta.get_text()).lower()
        valor = li.find("span")
        if clave.startswith("categor") and valor is not None:
            campos["categorias"] = [_limpia(s.get_text()) for s in valor.find_all("span")] or [
                _limpia(valor.get_text())
            ]
        elif clave == "emisor" and valor is not None:
            campos["emisor"] = _limpia(valor.get_text())
    anexos = []
    for a in soup.select("div.annexes a[href]"):
        for sr in a.select(".sr-only"):
            sr.decompose()
        anexos.append((_limpia(a.get_text()), urljoin(BASE_URL, a["href"])))
    return Detalle(
        categorias=campos.get("categorias", []),
        emisor=campos.get("emisor", ""),
        anexos=anexos,
    )


class Tablon:
    def __init__(self, timeout: float = 30.0):
        self._client = httpx.AsyncClient(headers=HEADERS, timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def pagina(
        self,
        page: int = 1,
        *,
        titulo: str = "",
        categoria: str = "",
        desde: date | None = None,
        hasta: date | None = None,
    ) -> tuple[list[Anuncio], bool]:
        # Sin path=buscar/ la web devuelve la tabla vacía.
        params = {
            "page": page,
            "title": titulo,
            "description": "",
            "categories": categoria,
            "fecha_ini": desde.strftime("%d/%m/%Y") if desde else "",
            "fecha_fin": hasta.strftime("%d/%m/%Y") if hasta else "",
            "path": "buscar/",
        }
        resp = await self._client.get(TABLON_URL, params=params)
        resp.raise_for_status()
        return parse_pagina(resp.text)

    async def detalle(self, anuncio: Anuncio) -> Detalle:
        resp = await self._client.get(anuncio.url)
        resp.raise_for_status()
        return parse_detalle(resp.text)

    async def buscar(self, max_paginas: int = 5, limite: int | None = None, **filtros) -> list[Anuncio]:
        """Recorre varias páginas aplicando filtros (titulo, categoria, desde, hasta)."""
        resultado: list[Anuncio] = []
        for page in range(1, max_paginas + 1):
            anuncios, hay_siguiente = await self.pagina(page, **filtros)
            resultado.extend(anuncios)
            if limite and len(resultado) >= limite:
                return resultado[:limite]
            if not hay_siguiente:
                break
        return resultado

    async def del_dia(self, dia: date) -> list[Anuncio]:
        return await self.buscar(max_paginas=10, desde=dia, hasta=dia)

    async def recientes(self, n: int = 20) -> list[Anuncio]:
        return await self.buscar(max_paginas=(n // 10) + 1, limite=n)
