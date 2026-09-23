import asyncio
from datetime import date

import httpx
import pytest

from tablon import Tablon
from tests.test_tablon import fila, pagina


class Web:
    """Simula el tablón: 3 páginas de 2 anuncios cada una."""

    def __init__(self):
        self.peticiones = []

    def __call__(self, request):
        self.peticiones.append(request)
        if "/anuncio/" in request.url.path:
            return httpx.Response(200, text='<ul class="list-group"></ul>')
        page = int(request.url.params["page"])
        ids = {1: [6, 5], 2: [4, 3], 3: [2, 1]}[page]
        return httpx.Response(200, text=pagina([fila(i) for i in ids], siguiente=page < 3))


@pytest.fixture
def web():
    return Web()


def ejecutar(web, corrutina):
    async def run():
        tablon = Tablon()
        await tablon._client.aclose()
        tablon._client = httpx.AsyncClient(transport=httpx.MockTransport(web))
        try:
            return await corrutina(tablon)
        finally:
            await tablon.close()

    return asyncio.run(run())


def test_pagina_envia_los_parametros_de_busqueda(web):
    anuncios, hay_siguiente = ejecutar(
        web, lambda t: t.pagina(2, titulo="beca", desde=date(2026, 9, 1), hasta=date(2026, 9, 23))
    )
    params = web.peticiones[0].url.params
    assert [a.id for a in anuncios] == [4, 3]
    assert hay_siguiente is True
    assert params["path"] == "buscar/"
    assert params["title"] == "beca"
    assert params["fecha_ini"] == "01/09/2026"
    assert params["fecha_fin"] == "23/09/2026"


def test_buscar_recorre_hasta_la_ultima_pagina(web):
    anuncios = ejecutar(web, lambda t: t.buscar(max_paginas=10))
    assert [a.id for a in anuncios] == [6, 5, 4, 3, 2, 1]
    assert len(web.peticiones) == 3


def test_recientes_respeta_el_limite(web):
    # recientes() supone 10 anuncios por página, como la web real: n=1 solo pide la primera.
    anuncios = ejecutar(web, lambda t: t.recientes(1))
    assert [a.id for a in anuncios] == [6]
    assert len(web.peticiones) == 1


def test_del_dia_filtra_por_fecha(web):
    ejecutar(web, lambda t: t.del_dia(date(2026, 9, 23)))
    params = web.peticiones[0].url.params
    assert params["fecha_ini"] == params["fecha_fin"] == "23/09/2026"


def test_detalle(web):
    async def detalle(t):
        anuncios, _ = await t.pagina(1)
        return await t.detalle(anuncios[0])

    d = ejecutar(web, detalle)
    assert d.categorias == []
    assert web.peticiones[-1].url.path == "/tablon-oficial/anuncio/6/"


def test_error_http(web):
    def caida(request):
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        ejecutar(caida, lambda t: t.pagina(1))
