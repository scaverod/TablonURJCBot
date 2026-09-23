import asyncio
import json
from datetime import datetime

import httpx
import pytest

import bot
from tablon import Anuncio


def anuncio(id_, titulo="Anuncio", inicio=datetime(2026, 9, 23, 9, 45)):
    return Anuncio(
        id=id_,
        titulo=titulo,
        descripcion="",
        url=f"https://sede.urjc.es/tablon-oficial/anuncio/{id_}/",
        inicio=inicio,
        fin=None,
    )


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    async def dormir(_):
        return None

    monkeypatch.setattr(bot.asyncio, "sleep", dormir)


class TestConfiguracion:
    def test_chat_ids_separados_por_comas(self):
        assert bot.CHAT_IDS == ["111", "222"]


class TestEstado:
    def test_sin_fichero_devuelve_vacio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "ESTADO_PATH", tmp_path / "estado.json")
        assert bot.cargar_vistos() == set()

    def test_guardar_y_cargar(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "ESTADO_PATH", tmp_path / "estado.json")
        bot.guardar_vistos({3, 1, 2})
        assert bot.cargar_vistos() == {1, 2, 3}
        assert json.loads((tmp_path / "estado.json").read_text()) == {"vistos": [1, 2, 3]}

    def test_guarda_solo_los_mas_recientes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "ESTADO_PATH", tmp_path / "estado.json")
        monkeypatch.setattr(bot, "MAX_VISTOS", 3)
        bot.guardar_vistos({1, 2, 3, 4, 5})
        assert bot.cargar_vistos() == {3, 4, 5}


class TestFormato:
    def test_linea_escapa_html(self):
        ln = bot.linea(anuncio(1, titulo="Becas <2026> & más"))
        assert "Becas &lt;2026&gt; &amp; más" in ln
        assert '<a href="https://sede.urjc.es/tablon-oficial/anuncio/1/">' in ln
        assert ln.endswith("<i>(23/09 09:45)</i>")

    def test_linea_sin_fecha(self):
        assert "<i>" not in bot.linea(anuncio(1, inicio=None))

    def test_linea_recorta_titulos_largos(self):
        ln = bot.linea(anuncio(1, titulo="x" * (bot.MAX_TITULO + 50)))
        assert "x" * (bot.MAX_TITULO - 1) + "…" in ln
        assert "x" * bot.MAX_TITULO not in ln

    def test_resumen_en_un_mensaje(self):
        mensajes = bot.componer_resumen([anuncio(1), anuncio(2)], truncado=False)
        assert len(mensajes) == 1
        texto, ids = mensajes[0]
        assert ids == [1, 2]
        assert texto.startswith("📋 <b>Tablón URJC – 2 anuncio(s) nuevo(s)</b>\n\n")
        assert "(1/1)" not in texto

    def test_resumen_largo_se_parte_sin_pasar_del_limite(self):
        nuevos = [anuncio(i, titulo="t" * 300) for i in range(100)]
        mensajes = bot.componer_resumen(nuevos, truncado=False)

        assert len(mensajes) > 1
        assert [i for _, ids in mensajes for i in ids] == list(range(100))
        for n, (texto, _) in enumerate(mensajes, 1):
            assert f"({n}/{len(mensajes)})" in texto
            assert len(texto) <= 4096

    def test_aviso_de_truncado_solo_en_el_ultimo(self):
        nuevos = [anuncio(i, titulo="t" * 300) for i in range(30)]
        mensajes = bot.componer_resumen(nuevos, truncado=True)
        avisos = ["⚠️" in texto for texto, _ in mensajes]
        assert avisos == [False] * (len(mensajes) - 1) + [True]


class TablonFalso:
    def __init__(self, paginas):
        self.paginas = paginas
        self.pedidas = []

    async def pagina(self, page):
        self.pedidas.append(page)
        ids = self.paginas[page - 1]
        return [anuncio(i) for i in ids], page < len(self.paginas)


class TestAnunciosNuevos:
    def test_para_al_encontrar_uno_visto(self):
        tablon = TablonFalso([[30, 29, 28], [27, 26, 25], [24, 23, 22]])
        nuevos, truncado = asyncio.run(bot.anuncios_nuevos(tablon, vistos={26, 25, 24}))
        assert [a.id for a in nuevos] == [30, 29, 28, 27]
        assert truncado is False
        assert tablon.pedidas == [1, 2]

    def test_para_en_la_ultima_pagina(self):
        tablon = TablonFalso([[2, 1]])
        nuevos, truncado = asyncio.run(bot.anuncios_nuevos(tablon, vistos=set()))
        assert [a.id for a in nuevos] == [2, 1]
        assert truncado is False

    def test_corta_en_max_paginas(self, monkeypatch):
        monkeypatch.setattr(bot, "MAX_PAGINAS", 2)
        tablon = TablonFalso([[6, 5], [4, 3], [2, 1]])
        nuevos, truncado = asyncio.run(bot.anuncios_nuevos(tablon, vistos=set()))
        assert [a.id for a in nuevos] == [6, 5, 4, 3]
        assert truncado is True


def cliente(respuestas, peticiones):
    """Cliente httpx que devuelve las respuestas indicadas en orden."""
    cola = list(respuestas)

    def manejar(request):
        peticiones.append(json.loads(request.content))
        return cola.pop(0)

    return httpx.AsyncClient(transport=httpx.MockTransport(manejar))


async def enviar_con(respuestas, peticiones):
    async with cliente(respuestas, peticiones) as c:
        await bot.enviar(c, "hola")


class TestEnviar:
    def test_envia_a_todos_los_chats(self):
        peticiones = []
        asyncio.run(enviar_con([httpx.Response(200), httpx.Response(200)], peticiones))
        assert [p["chat_id"] for p in peticiones] == ["111", "222"]
        assert peticiones[0]["parse_mode"] == "HTML"
        assert peticiones[0]["text"] == "hola"

    def test_reintenta_tras_429_y_errores_del_servidor(self):
        peticiones = []
        respuestas = [
            httpx.Response(429, json={"parameters": {"retry_after": 3}}),
            httpx.Response(502),
            httpx.Response(200),
            httpx.Response(200),
        ]
        asyncio.run(enviar_con(respuestas, peticiones))
        assert [p["chat_id"] for p in peticiones] == ["111", "111", "111", "222"]

    def test_falla_con_error_del_cliente(self):
        with pytest.raises(RuntimeError, match="400"):
            asyncio.run(enviar_con([httpx.Response(400, text="Bad Request")], []))

    def test_se_rinde_tras_varios_intentos(self):
        respuestas = [httpx.Response(500)] * bot.REINTENTOS
        with pytest.raises(RuntimeError, match="tras"):
            asyncio.run(enviar_con(respuestas, []))


class TestMain:
    @pytest.fixture
    def entorno(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "ESTADO_PATH", tmp_path / "estado.json")
        monkeypatch.setattr(bot, "CHAT_IDS", ["111"])
        enviados = []

        class Tablon:
            ids = [3, 2, 1]

            async def pagina(self, page):
                return [anuncio(i) for i in self.ids], False

            async def close(self):
                pass

        async def enviar(_client, texto):
            enviados.append(texto)

        monkeypatch.setattr(bot, "Tablon", Tablon)
        monkeypatch.setattr(bot, "enviar", enviar)
        return Tablon, enviados

    def test_primera_ejecucion_solo_confirma(self, entorno):
        _, enviados = entorno
        asyncio.run(bot.main())
        assert len(enviados) == 1
        assert "configurado" in enviados[0]
        assert bot.cargar_vistos() == {1, 2, 3}

    def test_sin_novedades_no_envia(self, entorno):
        _, enviados = entorno
        bot.guardar_vistos({1, 2, 3})
        asyncio.run(bot.main())
        assert enviados == []

    def test_envia_los_nuevos_del_mas_antiguo_al_mas_reciente(self, entorno):
        tablon, enviados = entorno
        tablon.ids = [5, 4, 3]
        bot.guardar_vistos({1, 2, 3})
        asyncio.run(bot.main())
        assert len(enviados) == 1
        assert enviados[0].index("anuncio/4/") < enviados[0].index("anuncio/5/")
        assert bot.cargar_vistos() == {1, 2, 3, 4, 5}

    def test_guarda_el_progreso_si_falla_a_mitad(self, entorno, monkeypatch):
        tablon, _ = entorno
        tablon.ids = list(range(40, 3, -1))
        bot.guardar_vistos({1, 2, 3})
        monkeypatch.setattr(bot, "MAX_MSG", 300)  # unos pocos anuncios por mensaje
        llamadas = []

        async def enviar(_client, texto):
            llamadas.append(texto)
            if len(llamadas) == 2:
                raise RuntimeError("Telegram caído")

        monkeypatch.setattr(bot, "enviar", enviar)
        with pytest.raises(RuntimeError):
            asyncio.run(bot.main())

        enviados_ok = {a for a in range(4, 41) if f"anuncio/{a}/" in llamadas[0]}
        assert enviados_ok
        assert bot.cargar_vistos() == {1, 2, 3} | enviados_ok
