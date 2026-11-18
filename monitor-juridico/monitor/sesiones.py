"""Sesiones del Pleno de la SCJN a partir de las versiones taquigráficas (PDF).

Listado: https://www.scjn.gob.mx/multimedia/versiones-taquigraficas
Cada PDF trae:
  - un ÍNDICE con cada asunto: número, descripción, ponencia y estado
    (RESUELTO/A, EN LISTA, RETIRADO, APLAZADO, NO EJERCE…);
  - el debate, donde el Secretario General de Acuerdos informa las votaciones
    ("me permito informarle que existe mayoría de ocho votos…") y las personas
    ministras anuncian votos concurrentes, particulares o aclaratorios.
Todo se extrae con reglas fijas (expresiones regulares), sin IA.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, asdict, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .http import nueva_sesion, pausa

SITIO = "https://www.scjn.gob.mx"
LISTADO = SITIO + "/multimedia/versiones-taquigraficas?page={pagina}"

ESTADOS = (r"RESUELT[OA]S?|EN LISTA|RETIRAD[OA]S?|APLAZAD[OA]S?|NO EJERCE|SE EJERCE|EJERCE|NO REASUME|REASUME|"
           r"DESECHAD[OA]|SOBRESE[ÍI]D[OA]|DESIERT[OA]|INEXISTENTE|EXISTENTE|IMPROCEDENTE|SIN MATERIA")
NUMERO = r"\d{1,5}/\d{4}(?:-[A-Z]{1,3})?(?: Y (?:SUS? )?ACUMULAD[OA]S? (?:\d{1,5}(?:/\d{4})?(?:, | Y )?)+)?"
_ENTRADA = re.compile(r"(?<![\w/])(" + NUMERO + r") (?=[A-ZÁÉÍÓÚÑ]{3,})")
_PONENCIA = re.compile(
    r"\(PONENCIA (?:DE LA|DEL|DE) (?:SEÑORA? )?(?:MINISTR[OA] )?(?:PRESIDENT[EA] )?([A-ZÁÉÍÓÚÑ ]+?)\)\.?")
_ESTADO = re.compile(rf"\b({ESTADOS})\b")
_PAGINAS = re.compile(r"\b\d{1,3}(?: (?:A|Y) \d{1,3})?\b(?= (?:" + ESTADOS + r"))")
_TIPO = re.compile(r"^(.*?)(?= PROMOVID| INTERPUEST| SUSCITAD| FORMULAD| RESPECTO| DEMANDANDO| EN CONTRA|,|\.|$)")
_ORADOR = re.compile(
    r"(SEÑORA? MINISTR[OA](?: PRESIDENT[EA])?(?: [A-ZÁÉÍÓÚÑ]+){0,3}|SECRETARI[OA] GENERAL DE ACUERDOS):")
_VOTO = re.compile(r"\bvotos? (concurrente|particular|aclaratorio|razonado|de minor[ií]a)", re.I)
_PRIMERA_PERSONA = re.compile(
    r"\b(anuncio|haré|hago|formularé|formulo|emitiré|elaboraré|reservo|me reservo|reservarme|reservar|"
    r"tengo reserva|haré reserva|voy a (?:emitir|hacer|formular|votar|estar|reservar)|con (?:un |reserva de |mi )?votos?)\b", re.I)
_DISCUSION = re.compile(r"cada quien|pueden formular|será parte de|acepto (?:los|el) votos?|uno sostiene|hay algunos como", re.I)
_DECISION = re.compile(
    r"((?:[A-ZÁÉÍÓÚÑ0-9/,;]+ ){3,}?(?:RESUELT[OA]S?|SE EJERCE|NO SE EJERCE|SE APLAZA|SE RETIRA|SE DESECHA)(?: [A-ZÁÉÍÓÚÑ0-9/,;.]+)*\.)")
_FECHA = re.compile(r"CELEBRADA EL \w+ (\d{1,2} DE \w+ DE \d{4})")


@dataclass
class Sesion:
    url: str
    fecha: str
    asuntos: list[dict] = field(default_factory=list)  # {numero, tipo, descripcion, ponente, estado}
    votaciones: list[str] = field(default_factory=list)  # lo que informa la Secretaría
    votos_anunciados: list[dict] = field(default_factory=list)  # {quien, texto}
    decisiones: list[str] = field(default_factory=list)  # declaraciones de la Presidencia

    def dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ listado
def parsear_listado(html_texto: str) -> list[dict]:
    """Tabla Fecha | Instancia | Documento → [{fecha, instancia, url}] (más reciente primero)."""
    sopa = BeautifulSoup(html_texto, "html.parser")
    filas = []
    for tr in sopa.find_all("tr"):
        a = tr.find("a", href=re.compile(r"\.pdf", re.I))
        if not a:
            continue
        celdas = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        filas.append({
            "fecha": celdas[0] if celdas else "",
            "instancia": celdas[1] if len(celdas) > 2 else "",
            "url": urljoin(SITIO, a["href"]),
        })
    return filas


# ------------------------------------------------------------- texto del PDF
def texto_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader
    lector = PdfReader(io.BytesIO(contenido))
    paginas = []
    for p in lector.pages:
        t = p.extract_text() or ""
        # el número de página (y adornos) queda al inicio o al final del texto de cada hoja;
        # si no se quita, aparece a media frase al unir las páginas ("Aguilar 49 Ortiz")
        t = re.sub(r"^[\s“”_]*\d{1,3}[\s“”_]*(?=\S)", "", t)
        t = re.sub(r"(?<=\S)[\s“”_]+\d{1,3}[\s“”_]*$", "", t)
        paginas.append(t)
    return "\n".join(paginas)


_LINEA_BASURA = re.compile(r"^[\s“”_]*$")


def _plano(texto: str) -> str:
    """Une el texto en una sola línea, quitando números de página y adornos."""
    lineas = [l for l in texto.replace("\f", "\n").splitlines() if not _LINEA_BASURA.match(l)]
    texto = " ".join(lineas).replace("“", " ").replace("”", " ")
    texto = re.sub(r"(\d) /\s*(\d{4})", r"\1/\2", texto)  # expediente partido en dos renglones
    return re.sub(r"\s+", " ", texto).strip()


_ROMANO = re.compile(r"^[IVXLC]+[.,]?$")


def _titulo(s: str) -> str:
    menores = {"de", "del", "la", "las", "los", "el", "en", "y", "a", "por", "para"}
    salida = []
    for i, p in enumerate(s.split()):
        if _ROMANO.match(p) and p not in ("DE", "LA"):
            salida.append(p)  # fracción III, artículo 105…
        elif i and p.lower() in menores:
            salida.append(p.lower())
        else:
            salida.append(p.capitalize())
    return " ".join(salida)


# ----------------------------------------------------------------- análisis
def parsear_indice(plano: str) -> list[dict]:
    ini = plano.find("SECRETARÍA GENERAL DE ACUERDOS")
    m_fin = re.compile(r"TRIBUNAL PLENO SESI[ÓO]N").search(plano, ini + 1) if ini >= 0 else None
    if not m_fin:
        return []
    fin = m_fin.start()
    indice = plano[ini + len("SECRETARÍA GENERAL DE ACUERDOS"):fin]
    indice = re.sub(r"SUPREMA CORTE DE JUSTICIA DE LA NACIÓN\s*$", "", indice)
    cortes = [m.start() for m in _ENTRADA.finditer(indice)] + [len(indice)]
    asuntos = []
    for a, b in zip(cortes, cortes[1:]):
        trozo = indice[a:b].strip()
        num = _ENTRADA.match(trozo).group(1)
        resto = trozo[len(num):].strip()
        pon = _PONENCIA.search(resto)
        est = _ESTADO.findall(resto)
        desc = _PONENCIA.sub(" ", resto)
        desc = _PAGINAS.sub(" ", desc)
        desc = _ESTADO.sub(" ", desc)
        # restos de la columna de páginas del índice ("37 A 43", "2843")
        desc = re.sub(r"\b\d{1,3} (?:A|Y) \d{1,3}\b", " ", desc)
        desc = re.sub(r"(?<![/\d])\b(?!19\d\d|20\d\d)\d{4}\b(?![/\d])", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip(" .")
        tipo = _TIPO.match(desc).group(1).strip()
        asuntos.append({
            "numero": num,
            "tipo": _titulo(tipo),
            "descripcion": desc,
            "ponente": _titulo(pon.group(1)) if pon else "",
            "estado": _estado_legible(est[-1]) if est else "",
        })
    return asuntos


def _estado_legible(e: str) -> str:
    for raiz, nombre in (("RESUELT", "Resueltos"), ("RETIRAD", "Retirados"), ("APLAZAD", "Aplazados"),
                         ("EN LISTA", "Quedaron en lista"), ("NO EJERCE", "No se ejerce la facultad de atracción"),
                         ("SE EJERCE", "Se ejerce la facultad de atracción"), ("EJERCE", "Se ejerce la facultad de atracción"),
                         ("NO REASUME", "No se reasume competencia"), ("REASUME", "Se reasume competencia"),
                         ("DESECHAD", "Desechados"), ("SOBRESE", "Sobreseídos"), ("DESIERT", "Desiertos"),
                         ("INEXISTENTE", "Contradicción inexistente"), ("EXISTENTE", "Contradicción existente"),
                         ("IMPROCEDENTE", "Improcedentes"), ("SIN MATERIA", "Sin materia")):
        if e.startswith(raiz):
            return nombre
    return e.capitalize()


def _bloques(cuerpo: str) -> list[tuple[str, str]]:
    partes = _ORADOR.split(cuerpo)
    return [(partes[i].strip(), partes[i + 1].strip()) for i in range(1, len(partes) - 1, 2)]


def _oraciones(texto: str) -> list[str]:
    return [o.strip() for o in re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ¿“])", texto) if o.strip()]


def parsear_debate(plano: str) -> tuple[list[str], list[dict], list[str]]:
    inicio = plano.find("(SE ABRIÓ LA SESIÓN")
    cuerpo = plano[inicio:] if inicio >= 0 else plano
    votaciones, votos, decisiones = [], [], []
    for orador, texto in _bloques(cuerpo):
        if orador.startswith("SECRETARI"):
            i = texto.lower().find("me permito informarle")
            if i >= 0:
                fragmento = texto[i:]
                fragmento = fragmento[0].upper() + fragmento[1:]
                votaciones.append(fragmento[:900] + ("…" if len(fragmento) > 900 else ""))
        else:
            quien = re.sub(r"^SEÑORA? MINISTR[OA] ", "", orador)
            quien = _titulo(quien.replace("PRESIDENTE ", "Presidente ") if quien != "PRESIDENTE" else "Presidente")
            for o in _oraciones(texto):
                if _VOTO.search(o) and _PRIMERA_PERSONA.search(o) and not _DISCUSION.search(o):
                    votos.append({"quien": quien, "texto": o[:300] + ("…" if len(o) > 300 else "")})
            if "PRESIDENT" in orador:
                for m in _DECISION.finditer(texto):
                    d = m.group(1).strip()
                    if len(d) > 30:
                        decisiones.append(d[:400])
    return votaciones, votos, decisiones


def parsear_sesion(texto: str, url: str, fecha_listado: str = "") -> Sesion:
    plano = _plano(texto)
    f = _FECHA.search(plano)
    votaciones, votos, decisiones = parsear_debate(plano)
    return Sesion(
        url=url,
        fecha=_titulo(f.group(1)) if f else fecha_listado,
        asuntos=parsear_indice(plano),
        votaciones=votaciones,
        votos_anunciados=votos,
        decisiones=decisiones,
    )


# ------------------------------------------------------------------- flujo
def obtener_nuevas(vistas: set[str], max_nuevas: int = 6, inicial: bool = False) -> list[Sesion]:
    s = nueva_sesion()
    r = s.get(LISTADO.format(pagina=0), timeout=30)
    r.raise_for_status()
    filas = []
    for f in parsear_listado(r.text):  # el listado va de la más reciente a la más antigua
        if f["url"] in vistas:
            break  # todo lo que sigue ya es anterior a la última sesión enviada
        filas.append(f)
    if inicial:
        filas = filas[:2]  # la primera vez, solo las dos sesiones más recientes
    sesiones = []
    for f in reversed(filas[:max_nuevas]):  # de la más antigua a la más reciente
        pausa(1)
        pdf = s.get(f["url"], timeout=90)
        pdf.raise_for_status()
        sesiones.append(parsear_sesion(texto_pdf(pdf.content), f["url"], f["fecha"]))
    return sesiones
