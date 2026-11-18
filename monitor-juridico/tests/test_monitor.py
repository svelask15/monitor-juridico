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
    def test_encabezados_y_licitaciones(self):
        data = {"NotasMatutinas": [
            {"codNota": 1, "fecha": "17-11-2026", "nombreCodOrgaUno": "PODER JUDICIAL", "codOrgaDos": "SUPREMA CORTE DE JUSTICIA DE LA NACION"},
            {"codNota": 2, "titulo": "COMISION NACIONAL DE LOS DERECHOS HUMANOS - REF:582467", "fecha": "17-11-2026",
             "nombreCodOrgaUno": "", "codOrgaDos": "CONVOCATORIAS PARA CONCURSOS DE ADQUISICIONES"}]}
        notas = dof.parsear_dia(data)
        self.assertEqual([n.codigo for n in notas], [2])  # el encabezado sin título se descarta
        c = clasificar(notas[0], ["derechos humanos"])
        self.assertEqual((c["prioridad"], c["palabras_clave"]), (4, []))

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
        self.assertIn("criterio que queda sin efectos", alertas)
        self.assertTrue(t.contradiccion)
        refs = " ".join(t.referencias)
        self.assertIn("2019876", refs)
        self.assertIn("P./J. 4/2019", refs)
        self.assertTrue(sjf.instancia_permitida(t, ["Pleno"]))
        self.assertFalse(sjf.instancia_permitida(t, ["Plenos Regionales"]))
        t2 = sjf.parsear_tesis({**TESIS_API, "instancia": "Pleno de la Suprema Corte de Justicia de la Nación"})
        self.assertTrue(sjf.instancia_permitida(t2, ["Pleno", "Suprema Corte"]))

    def test_contradiccion_no_es_alerta(self):
        t = sjf.parsear_tesis({**TESIS_API, "texto": "Criterio jurídico: procede la suspensión.",
                                "fechaPublicacion": "2026-10-30 10:40:00.0"})
        self.assertEqual(sjf.detectar_cambios_vigencia(t), [])
        self.assertTrue(t.contradiccion)
        self.assertEqual(t.fecha_publicacion, "30/10/2026")

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
        self.assertIn("Jurisprudencia nueva de la SCJN", md)
        self.assertIn("Cambio de criterio", md)
        self.assertIn("Reformas a la Constitución", md)
        self.assertNotIn("licitación", md)  # prioridad 4 queda fuera
        html = reporte.html_desde_markdown(md)
        self.assertIn('<a href="https://sjf2.scjn.gob.mx/detalle/tesis/2031234">', html)


if __name__ == "__main__":
    unittest.main()


class PruebasCorrecciones(unittest.TestCase):
    def test_campos_numericos_semanario(self):
        t = sjf.parsear_tesis({**TESIS_API, "ta_tj": 1, "tipoTesis": None, "tipoDocumento": 2,
                                "fechaPublicacion": 1763164800000})
        self.assertEqual(t.tipo, "Jurisprudencia")
        self.assertEqual(t.fecha_publicacion, "15/11/2025")

    def test_listado_comunicados(self):
        html = """<table><thead><tr><th>Comunicado</th><th>Tema</th></tr></thead><tbody>
        <tr><td>Comunicado 162</td><td><a href="https://www.internet2.scjn.gob.mx/red2/comunicados/comunicado.asp?id=8586"
          title="Este comunicado se abrirá en una nueva página.">La Suprema Corte fija límites al acceso a datos.</a></td></tr>
        <tr><td>Comunicado 161</td><td><a href="https://www.internet2.scjn.gob.mx/red2/comunicados/comunicado.asp?id=8585">Otro tema.</a></td></tr>
        </tbody></table>"""
        filas = comunicados.parsear_listado(html)
        self.assertEqual(filas[0], {"id": 8586, "numero": "162", "titulo": "La Suprema Corte fija límites al acceso a datos."})
        self.assertEqual(filas[1]["id"], 8585)


class PruebasSesiones(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from monitor import sesiones
        self.m = sesiones
        texto = (Path(__file__).parent / "fixtures" / "vt_extracto.txt").read_text(encoding="utf-8")
        self.s = sesiones.parsear_sesion(texto, "https://x/vt.pdf")

    def test_indice(self):
        a = {x["numero"]: x for x in self.s.asuntos}
        self.assertEqual(self.s.fecha, "12 de Noviembre de 2026")
        self.assertEqual(len(a), 6)
        self.assertEqual(a["24/2026-CA"]["estado"], "Resueltos")
        self.assertEqual(a["158/2026"]["ponente"], "Esquivel Mossa")  # índice partido entre páginas
        self.assertEqual(a["164/2026"]["ponente"], "Aguilar Ortiz")
        self.assertEqual(a["84/2026"]["estado"], "Quedaron en lista")
        self.assertEqual(a["1189/2026"]["estado"], "No se ejerce la facultad de atracción")
        self.assertEqual(a["25/2026"]["tipo"], "Acción de Inconstitucionalidad")

    def test_debate(self):
        self.assertEqual(len(self.s.votaciones), 2)
        self.assertIn("vota en contra el Ministro Figueroa Mejía", self.s.votaciones[1])
        quien = [v["quien"] for v in self.s.votos_anunciados]
        self.assertEqual(quien, ["Ríos González", "Batres Guadarrama"])
        self.assertTrue(any("NO SE EJERCE" in d for d in self.s.decisiones))

    def test_listado(self):
        html = """<table><tr><td>12 de Noviembre de 2026</td><td>Pleno</td>
        <td><a href="/sites/default/files/versiones-taquigraficas/documento/2026-11-13/12%20noviembre.pdf">x</a></td></tr></table>"""
        f = self.m.parsear_listado(html)
        self.assertEqual(f[0]["url"], "https://www.scjn.gob.mx/sites/default/files/versiones-taquigraficas/documento/2026-11-13/12%20noviembre.pdf")
        self.assertEqual(f[0]["instancia"], "Pleno")


class PruebasAgenda(unittest.TestCase):
    def test_lista(self):
        from pathlib import Path
        from monitor import agenda
        texto = (Path(__file__).parent / "fixtures" / "lista_extracto.txt").read_text(encoding="utf-8")
        urls = ["http://www2.scjn.gob.mx/Juridica/Engroses/Cerrados/Publico/Proyecto/2026/11/CC360_2026.pdf",
                "http://www2.scjn.gob.mx/Juridica/Engroses/Cerrados/Publico/Proyecto/2026/11/QUEJA_CC_y_AI1_2026_CA.pdf"]
        l = agenda.parsear_lista(texto, "u", "", urls)
        self.assertEqual(l.fecha, "19 de noviembre de 2026")
        a = {x["numero"]: x for x in l.asuntos}
        self.assertEqual(list(a), ["360/2026", "1/2026-CA", "271/2026", "2932/2022"])
        self.assertEqual(a["360/2026"]["tipo"], "Controversia Constitucional")
        self.assertEqual(a["360/2026"]["ponente"], "Guerrero García")
        self.assertTrue(a["360/2026"]["proyecto"].endswith("CC360_2026.pdf"))
        self.assertTrue(a["1/2026-CA"]["proyecto"].endswith("AI1_2026_CA.pdf"))
        self.assertEqual(a["1/2026-CA"]["tipo"], "Queja en la Controversia Constitucional")
        self.assertEqual(a["271/2026"]["ponente"], "Ortiz Ahlf")
        self.assertEqual(a["2932/2022"]["ponente"], "Aguilar Ortiz")
        self.assertEqual(a["2932/2022"]["listado_desde"], "2 de octubre de 2025")
        self.assertEqual(a["271/2026"]["proyecto"], "")
        self.assertNotIn("CURP", str(l.asuntos))
        self.assertEqual(agenda.fecha_iso("19 de noviembre de 2026"), "2026-11-19")


class PruebasCorrecciones2(unittest.TestCase):
    def test_lista_sin_ponencia_e_historial(self):
        from pathlib import Path
        from monitor import agenda
        texto = (Path(__file__).parent / "fixtures" / "lista_18nov.txt").read_text(encoding="utf-8")
        a = {x["numero"]: x for x in agenda.parsear_lista(texto, "u").asuntos}
        self.assertEqual(list(a), ["180/2026", "53/2026", "174/2024"])
        self.assertEqual(a["180/2026"]["ponente"], "")
        self.assertEqual(a["180/2026"]["tipo"], "Solicitud de Reasunción de Competencia")
        self.assertEqual(a["53/2026"]["ponente"], "Guerrero García")
        self.assertEqual(a["174/2024"]["tipo"], "Acción de Inconstitucionalidad")
        self.assertEqual(a["174/2024"]["listado_desde"], "7 de abril de 2025")
        self.assertIn("Retirado el 19 de agosto de 2026", a["174/2024"]["historial"])

    def test_indice_numeros_partidos_y_paginas(self):
        from monitor import sesiones
        texto = """CELEBRADA EL JUEVES 5 DE NOVIEMBRE DE 2026. SECRETARÍA GENERAL DE ACUERDOS
53
/2026-CA RECURSO DE RECLAMACIÓN EN LA CONTROVERSIA CONSTITUCIONAL INTERPUESTO EN CONTRA DE LA 2843
SENTENCIA. (PONENCIA DE LA SEÑORA MINISTRA HERRERÍAS GUERRA). 7 A 22 RESUELTO
94/2026 Y ACUMULADAS 95/2026 ACCIONES DE INCONSTITUCIONALIDAD PROMOVIDAS POR X. 3 EN LISTA
6/2026 SOLICITUD DE EJERCICIO DE LA FACULTAD DE ATRACCIÓN PREVISTA EN LA FRACCIÓN III DEL
ARTÍCULO 105. 5 Y 6 NO EJERCE
SUPREMA CORTE DE JUSTICIA DE LA NACIÓN TRIBUNAL PLENO SESIÓN PÚBLICA"""
        a = {x["numero"]: x for x in sesiones.parsear_indice(sesiones._plano(texto))}
        self.assertIn("53/2026-CA", a)
        self.assertNotIn("2843", a["53/2026-CA"]["descripcion"])
        self.assertIn("94/2026 Y ACUMULADAS 95/2026", a)
        self.assertIn("Fracción III", a["6/2026"]["tipo"])


class PruebasMaterias(unittest.TestCase):
    def test_clasificacion(self):
        from monitor.materias import clasificar, es_tramite
        self.assertIn("Penal", clasificar("Acción de Inconstitucionalidad", "invalidez del artículo 295 Bis del Código Penal"))
        self.assertNotIn("Derechos humanos", clasificar("juzgado en el estado de aguascalientes"))  # 'agua' no cuenta
        self.assertEqual(clasificar("Ley Federal del Trabajo"), ["Laboral y seguridad social"])
        self.assertTrue(es_tramite("Controversia Constitucional", "invalidez de la ley de ingresos del municipio de Ario"))
        self.assertFalse(es_tramite("Amparo en Revisión", ""))

    def test_filtrar(self):
        from monitor import reporte
        nov = {"dof": [{"codigo": 1, "fecha": "17-11-2026", "edicion": "Matutina", "titulo": "Acuerdo fiscal",
                        "poder": "", "organismo": "SAT", "pagina": 1, "url": "u", "categoria": "acuerdo",
                        "categoria_etiqueta": "x", "prioridad": 2, "palabras_clave": [], "materias": ["Fiscal"]},
                       {"codigo": 2, "fecha": "17-11-2026", "edicion": "Matutina", "titulo": "DECRETO constitucional",
                        "poder": "", "organismo": "PR", "pagina": 1, "url": "u2", "categoria": "constitucion",
                        "categoria_etiqueta": "x", "prioridad": 1, "palabras_clave": [], "materias": ["Constitucional"]}]}
        md = reporte.markdown("t", nov, 3, None, {"formato": "compacto", "interes": ["Penal"], "modo": "filtrar"})
        self.assertNotIn("Acuerdo fiscal", md)
        self.assertIn("DECRETO constitucional", md)  # lo prioritario siempre llega


class PruebasPagina(unittest.TestCase):
    def test_construir(self):
        import json, tempfile
        from pathlib import Path
        from monitor import agenda, pagina, sesiones
        F = Path(__file__).parent / "fixtures"
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "hist").mkdir()
            ses = sesiones.parsear_sesion((F / "vt_extracto.txt").read_text(encoding="utf-8"), "https://x/vt.pdf")
            lista = agenda.parsear_lista((F / "lista_extracto.txt").read_text(encoding="utf-8"), "https://x/l.pdf")
            (d / "hist" / "2026-11-18.json").write_text(json.dumps({"sesiones": [ses.dict()], "agenda": [lista.dict()]}))
            out = pagina.construir(d / "docs", d / "hist")
            self.assertTrue((out / "index.html").exists())
            js = (out / "datos" / "2026-11.js").read_text(encoding="utf-8")
            self.assertIn('"f":"sesion"', js)
            self.assertIn('"f":"agenda"', js)
            self.assertIn("accion de inconstitucionalidad|25/2026", js)
            self.assertNotRegex(lista.asuntos[1]["descripcion"], r" 2$")
