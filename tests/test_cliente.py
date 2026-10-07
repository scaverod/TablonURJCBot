import asyncio

import httpx
import pytest

from tablon import REINTENTOS, Tablon
from tests.test_tablon import fila, pagina


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    async def dormir(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", dormir)


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


def test_error_http_tras_reintentar():
    peticiones = []

    def manejar(request):
        peticiones.append(request)
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        ejecutar(manejar, 1)
    assert len(peticiones) == REINTENTOS


def test_error_4xx_no_reintenta():
    peticiones = []

    def manejar(request):
        peticiones.append(request)
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        ejecutar(manejar, 1)
    assert len(peticiones) == 1


def test_reintenta_si_falla_la_conexion():
    intentos = []

    def manejar(request):
        intentos.append(request)
        if len(intentos) == 1:
            raise httpx.ConnectError("conexión cortada", request=request)
        return httpx.Response(200, text=pagina([fila(4)]))

    anuncios, _ = ejecutar(manejar, 1)
    assert [a.id for a in anuncios] == [4]
    assert len(intentos) == 2
