import asyncio

import httpx
import pytest

from tablon import Tablon
from tests.test_tablon import fila, pagina


def ejecutar(manejar, page):
    async def run():
        tablon = Tablon()
        await tablon._client.aclose()
        tablon._client = httpx.AsyncClient(transport=httpx.MockTransport(manejar))
        try:
            return await tablon.pagina(page)
        finally:
            await tablon.close()

    return asyncio.run(run())


def test_pagina_pide_la_busqueda_y_la_parsea():
    peticiones = []

    def manejar(request):
        peticiones.append(request)
        return httpx.Response(200, text=pagina([fila(4), fila(3)]))

    anuncios, hay_siguiente = ejecutar(manejar, 2)

    params = peticiones[0].url.params
    assert [a.id for a in anuncios] == [4, 3]
    assert hay_siguiente is True
    assert peticiones[0].url.path == "/tablon-oficial"
    assert params["page"] == "2"
    assert params["path"] == "buscar/"


def test_error_http():
    with pytest.raises(httpx.HTTPStatusError):
        ejecutar(lambda request: httpx.Response(503), 1)
