from datetime import datetime

from tablon import _limpia, _parse_fecha, parse_pagina


def fila(id_, titulo="Título", descripcion="Descripción", inicio="23/09/2026 09:45:38", fin="24/09/2027 23:59:59"):
    return f"""
    <tr>
      <td><a class="noProxy" href="/tablon-oficial/anuncio/{id_}/">
          {titulo}
      </a></td>
      <td>
        {descripcion}
      </td>
      <td>{inicio}</td>
      <td>{fin}</td>
    </tr>"""


def pagina(filas, siguiente=True):
    paginacion = (
        '<a class="next noProxy" href="?page=2">siguiente ››</a>'
        if siguiente
        else '<span class="disabled next">siguiente ››</span>'
    )
    return f"""
    <html><body>
      <table id="result_list"><thead><tr><th>Título</th></tr></thead>
        <tbody>{"".join(filas)}</tbody>
      </table>
      <ul class="pagination"><li>{paginacion}</li></ul>
    </body></html>"""


class TestUtilidades:
    def test_parse_fecha_valida(self):
        assert _parse_fecha(" 23/09/2026 09:45:38 ") == datetime(2026, 9, 23, 9, 45, 38)

    def test_parse_fecha_invalida(self):
        assert _parse_fecha("") is None
        assert _parse_fecha("23/09/2026") is None

    def test_limpia_colapsa_espacios(self):
        assert _limpia("  hola\n\t  mundo  ") == "hola mundo"


class TestParsePagina:
    def test_extrae_anuncios(self):
        anuncios, hay_siguiente = parse_pagina(
            pagina([fila(16229, titulo="Convocatoria  BIP\n Erasmus+"), fila(16228)])
        )

        assert hay_siguiente is True
        assert [a.id for a in anuncios] == [16229, 16228]
        a = anuncios[0]
        assert a.titulo == "Convocatoria BIP Erasmus+"
        assert a.descripcion == "Descripción"
        assert a.url == "https://sede.urjc.es/tablon-oficial/anuncio/16229/"
        assert a.inicio == datetime(2026, 9, 23, 9, 45, 38)
        assert a.fin == datetime(2027, 9, 24, 23, 59, 59)

    def test_ultima_pagina(self):
        _, hay_siguiente = parse_pagina(pagina([fila(1)], siguiente=False))
        assert hay_siguiente is False

    def test_fechas_vacias(self):
        anuncios, _ = parse_pagina(pagina([fila(1, inicio="", fin="-")]))
        assert anuncios[0].inicio is None
        assert anuncios[0].fin is None

    def test_ignora_filas_incompletas_o_sin_enlace(self):
        incompleta = '<tr><td><a href="/tablon-oficial/anuncio/5/">x</a></td></tr>'
        sin_enlace = "<tr><td>a</td><td>b</td><td>c</td><td>d</td></tr>"
        anuncios, _ = parse_pagina(pagina([incompleta, sin_enlace, fila(7)]))
        assert [a.id for a in anuncios] == [7]

    def test_sin_tabla(self):
        assert parse_pagina("<html><body>Mantenimiento</body></html>") == ([], False)
