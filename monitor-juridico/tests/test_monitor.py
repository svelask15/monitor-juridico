"""Pruebas sin conexión con datos de ejemplo con la misma forma que las fuentes reales."""
import unittest

from monitor import comunicados, dof, reporte, sjf
from monitor.clasificar import clasificar

SIDOF = {
    "messageCode": 200, "response": "OK", "NotasExtraordinarias": [],
    "NotasMatutinas": [
        {"codNota": 5803757, "titulo": "Decreto por el que se expide la Ley de Ingresos de la Federación para el Ejercicio Fiscal de 2027.",
         "fecha": "13-11-2026", "pagina": 4, "nombreCodOrgaUno": "PODER EJECUTIVO", "codOrgaDos": "PRESIDENCIA DE LA REPUBLICA"},
        {"codNota": 5803760, "titulo": "Sentencia dictada por el Tribunal Pleno en la Acción de Inconstitucionalidad 130/2025, así como el voto concurrente.",
         "fecha": "13-11-2026", "pagina": 10, "nombreCodOrgaUno": "PODER JUDICIAL", "codOrgaDos": "SUPREMA CORTE DE JUSTICIA DE LA NACION"},
        {"codNota": 5803761, "titulo": "DECRETO por el que se reforma el artículo 4o. de la Constitución Política de los Estados Unidos Mexicanos.",
         "fecha": "13-11-2026", "pagina": 2, "nombreCodOrgaUno": "PODER EJECUTIVO", "codOrgaDos": "PRESIDENCIA DE LA REPUBLICA"},
    ],
    "NotasVespertinas": [
        {"codNota": 5803837, "titulo": "Decreto por el que se reforman, adicionan y derogan diversas disposiciones de la Ley de Amparo.",
         "fecha": "13-11-2026", "pagina": 3, "nombreCodOrgaUno": "PODER EJECUTIVO", "codOrgaDos": "PRESIDENCIA DE LA REPUBLICA"},
        {"codNota": 5803840, "titulo": "Aviso de licitación pública nacional.", "fecha": "13-11-2026",
         "nombreCodOrgaUno": "PODER EJECUTIVO", "codOrgaDos": "SECRETARIA DE SALUD"},
    ],
}

TESIS_API = {
    "ius": 2031234, "rubro": "<p>PRISIÓN PREVENTIVA OFICIOSA. SU APLICACIÓN DEBE ...</p>",
    "claveTesis": "P./J. 12/2026 (12a.)  ", "tipoTesis": "Jurisprudencia", "instancia": "Pleno",
    "materias": ["Constitucional", "Penal"], "epoca": "Duodécima Época",
    "fechaPublicacion": "14 de noviembre de 2026",
    "texto": "Hechos: ... Justificación: Este Tribunal Pleno se aparta del criterio sostenido en la tesis "
             "P./J. 4/2019 (10a.), con registro digital: 2019876, el cual queda sin efectos.",
    "precedentes": [{"asunto": "Contradicción de criterios 45/2026. 10 de agosto de 2026. Mayoría de seis votos."}],
    "votos": [{"tipoVoto": "Voto particular"}],
}

COMUNICADO_HTML = """<html><body><div>Suprema Corte de Justicia</div><div>Comunicados de Prensa</div>
<p>No.124/2026</p><p>Ciudad de México, 31 de agosto de 2026</p>
<p>LA SCJN GARANTIZA CERTEZA EN SANCIONES PENALES Y PROTEGE PENSIONES</p>
<p>El Pleno de la Suprema Corte de Justicia de la Nación invalidó por unanimidad de votos una porción normativa del código penal local.</p>
<p>Acciones de Inconstitucionalidad 127/2025 y su acumulada 133/2025. Resueltas en sesión de Pleno el 31 de agosto de 2026.</p>
<p>El Alto Tribunal resolvió que las aportaciones de personas jubiladas pueden ser válidas, por mayoría de seis votos.</p>
<p>Acción de Inconstitucionalidad 130/2025. Resuelta en sesión de Pleno el 31 de agosto de 2026.</p>
<p>Amparo Directo en Revisión 1038/2026. Resuelto en sesión de Pleno el 31 de agosto de 2026.</p>
</body></html>"""


class PruebasDOF(unittest.TestCase):
    def test_parseo_y_clasificacion(self):
        notas = dof.parsear_dia(SIDOF)
        self.assertEqual(len(notas), 5)
        cats = {n.codigo: clasificar(n, ["Ley de Amparo"])["categoria"] for n in notas}
        self.assertEqual(cats[5803757], "ley_nueva")
        self.assertEqual(cats[5803760], "scjn_sentencia")
        self.assertEqual(cats[5803761], "constitucion")
        self.assertEqual(cats[5803837], "reforma_legal")
        self.assertEqual(cats[5803840], "otros")
        self.assertIn("fecha=13/11/2026", notas[0].url)


class PruebasSemanario(unittest.TestCase):
    def test_parseo_y_vigencia(self):
        t = sjf.parsear_tesis(TESIS_API)
        self.assertEqual(t.registro, 2031234)
        self.assertEqual(t.clave, "P./J. 12/2026 (12a.)")
        self.assertEqual(t.tipo, "Jurisprudencia")
        self.assertNotIn("<p>", t.rubro)
        alertas = sjf.detectar_cambios_vigencia(t)
        texto = " ".join(alertas)
        self.assertIn("queda sin efectos", texto)
        self.assertIn("2019876", texto)
        self.assertIn("P./J. 4/2019", texto)
        self.assertTrue(sjf.instancia_permitida(t, ["Pleno"]))
        self.assertFalse(sjf.instancia_permitida(t, ["Plenos Regionales"]))

    def test_sin_falsos_positivos(self):
        t = sjf.parsear_tesis({**TESIS_API, "texto": "Hechos: ... Criterio jurídico: ...", "precedentes": []})
        self.assertEqual(sjf.detectar_cambios_vigencia(t), [])


class PruebasComunicados(unittest.TestCase):
    def test_parseo(self):
        c = comunicados.parsear(COMUNICADO_HTML, 8545)
        self.assertEqual(c.numero, "124/2026")
        self.assertEqual(c.fecha, "31 de agosto de 2026")
        self.assertTrue(c.titulo.startswith("LA SCJN GARANTIZA"))
        asuntos = [a["asunto"] for a in c.asuntos]
        self.assertEqual(len(asuntos), 3, asuntos)
        self.assertIn("Amparo Directo en Revisión 1038/2026", asuntos)
        self.assertTrue(any("unanimidad" in v for v in c.votaciones))

    def test_pagina_vacia(self):
        self.assertIsNone(comunicados.parsear("<html><body>Error</body></html>", 99999))


class PruebasReporte(unittest.TestCase):
    def test_reporte_completo(self):
        notas = [clasificar(n) for n in dof.parsear_dia(SIDOF)]
        t = sjf.parsear_tesis(TESIS_API)
        t.alertas_vigencia = sjf.detectar_cambios_vigencia(t)
        c = comunicados.parsear(COMUNICADO_HTML, 8545)
        nov = {"dof": notas, "tesis": [t.dict()], "comunicados": [c.dict()]}
        md = reporte.markdown("Prueba", nov, 2, ["Semanario: BloqueoFirewall"])
        self.assertIn("Criterios que podrían haber dejado de estar vigentes", md)
        self.assertIn("Reformas a la Constitución", md)
        self.assertNotIn("licitación", md)  # prioridad 4 queda fuera
        html = reporte.html_desde_markdown(md)
        self.assertIn('<a href="https://sjf2.scjn.gob.mx/detalle/tesis/2031234">', html)


if __name__ == "__main__":
    unittest.main()
