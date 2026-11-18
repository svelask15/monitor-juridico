"""Convierte textos en MAYÚSCULAS (como los del índice de las versiones
taquigráficas) a minúsculas respetando mayúsculas de nombres propios:
personas ministras, entidades federativas, órganos, leyes, municipios…
Reglas fijas; si algo sale mal, agrega el nombre a las listas de abajo.
"""
from __future__ import annotations

import re

MENORES = {"de", "del", "la", "las", "los", "el", "en", "y", "e", "a", "por", "para", "con", "al", "o", "u"}

NOMBRES = [
    # Pleno de la SCJN (integración 2025-2033)
    "Hugo Aguilar Ortiz", "Aguilar Ortiz", "Sara Irene Herrerías Guerra", "Herrerías Guerra",
    "Irving Espinosa Betanzo", "Espinosa Betanzo", "María Estela Ríos González", "Estela Ríos", "Ríos González",
    "Yasmín Esquivel Mossa", "Yasmín Esquivel", "Esquivel Mossa", "Lenia Batres Guadarrama", "Batres Guadarrama",
    "Loretta Ortiz Ahlf", "Ortiz Ahlf", "Giovanni Azael Figueroa Mejía", "Figueroa Mejía",
    "Arístides Rodrigo Guerrero García", "Guerrero García",
    # entidades federativas y ciudades frecuentes
    "Aguascalientes", "Baja California Sur", "Baja California", "Campeche", "Chiapas", "Chihuahua",
    "Ciudad de México", "Coahuila de Zaragoza", "Coahuila", "Colima", "Durango", "Guanajuato", "Guerrero",
    "Hidalgo", "Jalisco", "Estado de México", "México", "Michoacán de Ocampo", "Michoacán", "Morelos", "Nayarit",
    "Nuevo León", "Oaxaca", "Puebla", "Querétaro", "Quintana Roo", "San Luis Potosí", "Sinaloa", "Sonora",
    "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz de Ignacio de la Llave", "Veracruz", "Yucatán", "Zacatecas",
    "Zapopan", "Reynosa", "Chetumal", "Coatzacoalcos", "Matehuala", "Tijuana", "Monterrey", "Guadalajara",
    "Región Centro-Norte", "Región Centro-Sur", "Centro-Norte", "Centro-Sur",
    # órganos e instituciones
    "Suprema Corte de Justicia de la Nación", "Suprema Corte", "Tribunal Pleno", "Plenos Regionales", "Pleno Regional",
    "Primera Sala", "Segunda Sala", "Poder Ejecutivo Federal", "Poderes Ejecutivo y Legislativo",
    "Poderes Legislativo y Ejecutivo", "Poder Ejecutivo", "Poder Legislativo", "Poder Judicial de la Federación",
    "Poder Judicial", "Congreso de la Unión", "Congreso del Estado", "Cámara de Diputados", "Senado de la República",
    "Comisión Nacional de los Derechos Humanos", "Fiscalía General de la República", "Fiscalía General del Estado",
    "Fiscalía Especializada en Combate a la Corrupción", "Instituto Nacional Electoral", "Tribunal Electoral",
    "Órgano de Administración Judicial", "Tribunal de Disciplina Judicial", "Periódico Oficial", "Boletín Oficial",
    "Gaceta Oficial", "Diario Oficial de la Federación", "Semanario Judicial de la Federación",
    "Tribunal Federal de Justicia Administrativa", "Sala Superior", "Tribunal de Conciliación y Arbitraje",
    "Instituto Mexicano del Seguro Social", "Servicio de Administración Tributaria",
    "Comisión Federal de Competencia Económica", "Instituto Federal de Telecomunicaciones",
    "Instituto Morelense de Procesos Electorales y Participación Ciudadana", "Presidencia de la República",
    "Presidencia de la Suprema Corte de Justicia de la Nación", "Presidencia",
    "Constitución Política de los Estados Unidos Mexicanos", "Constitución Federal", "Constitución Política",
    "Ley de Amparo", "Ley Federal del Trabajo", "Código Nacional de Procedimientos Penales",
    "Partido del Trabajo", "Partido Verde Ecologista de México", "Partido Revolucionario Institucional",
    "Partido Acción Nacional", "Movimiento Ciudadano", "Nacional SOMOS", "LXV Legislatura", "LXVI Legislatura",
]
SIGLAS = {"morena": "MORENA", "somos": "SOMOS", "issste": "ISSSTE", "imss": "IMSS", "sat": "SAT", "cndh": "CNDH",
          "condusef": "CONDUSEF", "afore": "AFORE", "fgr": "FGR", "ine": "INE", "unam": "UNAM"}
ORDINALES = (r"(?:primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|sext[oa]|s[ée]ptim[oa]|octav[oa]|noven[oa]|"
             r"d[ée]cim[oa]\w*|decimo\w*|vig[ée]sim[oa]\w*|vigesimo\w*|trig[ée]sim[oa]\w*|trigesimo\w*|[uú]nic[oa])")


def _titulo(frase: str) -> str:
    palabras = frase.split(" ")
    salida = []
    for i, p in enumerate(palabras):
        if re.fullmatch(r"[ivxlc]+[.,]?", p) and len(p.strip(".,")) <= 5 and p.strip(".,") not in ("di", "vi", "mi"):
            salida.append(p.upper())  # fracción III
        elif i and p in MENORES:
            salida.append(p)
        else:
            salida.append(p[:1].upper() + p[1:])
    return " ".join(salida)


_NOMBRES = sorted(NOMBRES, key=len, reverse=True)
_PATRON_NOMBRES = re.compile(r"\b(" + "|".join(re.escape(n.lower()) for n in _NOMBRES) + r")\b")
_MAPA = {n.lower(): n for n in _NOMBRES}
_SIGLAS = re.compile(r"\b(" + "|".join(SIGLAS) + r")\b")
# Órganos jurisdiccionales: "primer tribunal colegiado en materia administrativa del primer circuito"
_ORGANO = re.compile(
    r"\b((?:" + ORDINALES + r" )?(?:tribunal(?:es)? colegiados?|juzgados?|plenos? regional(?:es)?|pleno)"
    r"(?: (?:de circuito|de apelaci[oó]n|de distrito))?(?: (?:" + ORDINALES + r"|y|en|de|del|la|las|materias?|"
    r"civil|penal|administrativa|del trabajo|de trabajo|trabajo|amparo|competencia|econ[oó]mica|radiodifusi[oó]n|"
    r"telecomunicaciones|especializados?|mercantil|familiar|apelaci[oó]n|centro|auxiliar|circuito|distrito|"
    r"regi[oó]n|primera|segunda|tercera|cuarta|quinta|sexta|s[ée]ptima|octava|novena|d[ée]cima|"
    r"administrativa,|civil,|penal,|,))*? (?:circuito|distrito|regi[oó]n))\b")
_LEY = re.compile(
    r"\b((?:ley|leyes|c[oó]digo|reglamento|constituci[oó]n pol[ií]tica|lineamientos)(?: (?:n[uú]mero \d+ )?"
    r"(?:[a-záéíóúñ]+))+?)(?=,|\.|;|\)| publicad| expedid| mediante| en (?:el|la|su)| respecto| que | para el ejercicio|$)")
_MUNICIPIO = re.compile(r"\b(municipio(?:s)? (?:libre )?de )((?:[a-záéíóúñ]+ ?){1,4}?)(?=,| del | para |\.| publicad| mediante|$)")
_MINISTRO = re.compile(r"\b(ministr[oa]s?|magistrad[oa]s?)(?= (?:presidente |instructor[a]? )?[A-ZÁÉÍÓÚ])")


def oracion(texto: str) -> str:
    """'PROMOVIDA POR EL PODER JUDICIAL DEL ESTADO DE MORELOS' → 'Promovida por el Poder Judicial del Estado de Morelos'."""
    if not texto:
        return texto
    letras = [c for c in texto if c.isalpha()]
    mayusculas = sum(c.isupper() for c in letras)
    if letras and 0 < mayusculas < 0.6 * len(letras):
        return texto[:1].upper() + texto[1:]  # ya viene con mayúsculas y minúsculas: no se toca
    t = texto.lower()
    t = _LEY.sub(lambda m: _titulo(m.group(1)), t)
    t = _ORGANO.sub(lambda m: _titulo(m.group(1)), t)
    t = _MUNICIPIO.sub(lambda m: m.group(1) + _titulo(m.group(2).strip()) + (" " if m.group(2).endswith(" ") else ""), t)
    t = re.sub(r"\bestado de (?=[a-záéíóúñ])", "Estado de ", t)
    t = re.sub(r"\bmunicipio de (?=[A-ZÁÉÍÓÚ])", "Municipio de ", t)
    t = re.sub(r"\b(fracci[oó]n(?:es)?|apartados?|t[ií]tulo|cap[ií]tulo|tema) ([ivxlc]+|[a-z])\b((?:(?:,| y| e) (?:[ivxlc]+|[a-z])\b)*)",
               lambda m: m.group(1) + " " + m.group(2).upper() + re.sub(r"((?:,| y| e) )([ivxlc]+|[a-z])\b", lambda x: x.group(1) + x.group(2).upper(), m.group(3)), t)
    t = _PATRON_NOMBRES.sub(lambda m: _MAPA[m.group(1)], t)
    t = _SIGLAS.sub(lambda m: SIGLAS[m.group(1)], t)
    t = _MINISTRO.sub(lambda m: m.group(1)[:1].upper() + m.group(1)[1:], t)
    t = re.sub(r"\bministr([oa]) presidente\b", lambda m: f"Ministr{m.group(1)} Presidente", t)
    return t[:1].upper() + t[1:]


def tipo(texto: str) -> str:
    """'CONTRADICCIÓN DE CRITERIOS' o 'Contradicción de Criterios' → 'Contradicción de criterios'."""
    return oracion((texto or "").upper())


_ACENTOS = {"republica": "república", "secretaria": "secretaría", "publica": "pública", "publico": "público",
            "publicos": "públicos", "economia": "economía", "energia": "energía", "organo": "órgano",
            "credito": "crédito", "tecnico": "técnico", "tecnologia": "tecnología", "mexico": "méxico",
            "geografia": "geografía", "estadistica": "estadística", "politica": "política", "indigenas": "indígenas",
            "fisica": "física", "medico": "médico", "academia": "academia", "agraria": "agraria", "rios": "ríos",
            "tribunal": "tribunal", "region": "región", "ejercito": "ejército", "aeronautica": "aeronáutica",
            "telecomunicaciones": "telecomunicaciones", "cientifica": "científica", "auditoria": "auditoría",
            "transito": "tránsito", "maritima": "marítima", "hidrocarburos": "hidrocarburos", "via": "vía"}


def nombre_organo(texto: str) -> str:
    """'SECRETARIA DE HACIENDA Y CREDITO PUBLICO' → 'Secretaría de Hacienda y Crédito Público'."""
    if not texto or not texto.isupper():
        return texto
    palabras = []
    for i, p in enumerate(texto.lower().split()):
        p = _ACENTOS.get(p, re.sub(r"cion$", "ción", re.sub(r"ciones$", "ciones", p)))
        palabras.append(p if (i and p in MENORES) else p[:1].upper() + p[1:])
    salida = " ".join(palabras)
    return re.sub(r"\b(Imss|Issste|Ine|Inegi|Sat|Pemex|Cfe|Conagua|Profeco|Condusef)\b", lambda m: m.group(1).upper(), salida)
