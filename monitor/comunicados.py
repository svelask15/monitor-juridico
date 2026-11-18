"""Comunicados de prensa de la SCJN: qué resolvió el Pleno en cada sesión.

Cada comunicado vive en
https://www.internet2.scjn.gob.mx/red2/comunicados/comunicado.asp?id=N
y los id son consecutivos, así que basta con probar id+1, id+2, ... hasta
encontrar varios vacíos seguidos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field

from bs4 import BeautifulSoup

from .http import nueva_sesion, pausa

URL = "https://www.internet2.scjn.gob.mx/red2/comunicados/comunicado.asp?id={id}"

_NUM = re.compile(r"No\.\s*(\d+/\d{4})")
_FECHA = re.compile(r"Ciudad de México,?\s+(?:a\s+)?(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})", re.I)
_ASUNTO = re.compile(
    r"([A-ZÁÉÍÓÚ][^.\n]{3,160}?\d+/\d{4}[^.\n]{0,160}?)\.\s*Resuelt[oa]s?\s+en\s+sesi[oó]n"
    r"(?:\s+(?:de|del)\s+(?:Pleno|Primera Sala|Segunda Sala))?(?:\s+(?:el|del)\s+([^.\n]{4,40}))?",
)
_VOTACION = re.compile(
    r"(unanimidad\s+de\s+(?:\w+\s+)?votos|mayor[ií]a\s+de\s+\w+\s+votos)", re.I
)


@dataclass
class Comunicado:
    id: int
    numero: str
    fecha: str
    titulo: str
    asuntos: list[dict] = field(default_factory=list)
    votaciones: list[str] = field(default_factory=list)
    resumen: str = ""

    @property
    def url(self) -> str:
        return URL.format(id=self.id)

    def dict(self) -> dict:
        d = asdict(self)
        d["url"] = self.url
        return d


def _es_titulo(linea: str) -> bool:
    letras = [c for c in linea if c.isalpha()]
    return len(letras) > 15 and sum(c.isupper() for c in letras) / len(letras) > 0.8


def parsear(html_texto: str, id_: int) -> Comunicado | None:
    sopa = BeautifulSoup(html_texto, "html.parser")
    for basura in sopa(["script", "style", "nav", "header", "footer"]):
        basura.decompose()
    texto = sopa.get_text("\n")
    lineas = [re.sub(r"\s+", " ", l).strip() for l in texto.splitlines()]
    lineas = [l for l in lineas if l]
    plano = "\n".join(lineas)

    num = _NUM.search(plano)
    if not num:
        return None  # id inexistente o página vacía
    fecha = _FECHA.search(plano)
    inicio = fecha.end() if fecha else num.end()
    resto = plano[inicio:]
    titulo = next((l for l in resto.splitlines() if _es_titulo(l)), "")

    asuntos = []
    vistos = set()
    for m in _ASUNTO.finditer(plano):
        nombre = re.sub(r"\s+", " ", m.group(1)).strip(" .•-")
        if nombre in vistos:
            continue
        vistos.add(nombre)
        asuntos.append({"asunto": nombre, "sesion": (m.group(2) or "").strip()})

    cuerpo = [l for l in resto.splitlines() if l != titulo and len(l) > 60]
    resumen = " ".join(cuerpo[:2])[:600]

    return Comunicado(
        id=id_,
        numero=num.group(1),
        fecha=fecha.group(1) if fecha else "",
        titulo=titulo,
        asuntos=asuntos,
        votaciones=sorted(set(v.strip() for v in _VOTACION.findall(plano)))[:10],
        resumen=resumen,
    )


LISTADO = "https://www.scjn.gob.mx/multimedia/comunicados?page={pagina}"
_ID = re.compile(r"comunicado\.asp\?id=(\d+)", re.I)
CABECERAS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.scjn.gob.mx/multimedia/comunicados",
}


def parsear_listado(html_texto: str) -> list[dict]:
    """Tabla 'Comunicado | Tema' de scjn.gob.mx → [{id, numero, titulo}]."""
    sopa = BeautifulSoup(html_texto, "html.parser")
    filas = []
    for a in sopa.find_all("a", href=_ID):
        id_ = int(_ID.search(a["href"]).group(1))
        tr = a.find_parent("tr")
        celdas = [c.get_text(" ", strip=True) for c in tr.find_all("td")] if tr else []
        numero = next((re.sub(r"\D", "", c) for c in celdas if re.search(r"comunicado\s*\d+|^\d+$", c, re.I)), "")
        filas.append({"id": id_, "numero": numero, "titulo": a.get_text(" ", strip=True)})
    return filas


def leer_listado(s, ultimo_id: int, max_paginas: int = 5) -> list[dict]:
    nuevos = {}
    for pagina in range(max_paginas):
        r = s.get(LISTADO.format(pagina=pagina), timeout=30, headers=CABECERAS)
        r.raise_for_status()
        filas = parsear_listado(r.text)
        for f in filas:
            if f["id"] > ultimo_id:
                nuevos[f["id"]] = f
        if not filas or min(f["id"] for f in filas) <= ultimo_id:
            break
        pausa(1)
    return [nuevos[k] for k in sorted(nuevos)]


def obtener_nuevos(ultimo_id: int, max_vacios: int = 4, max_nuevos: int = 60) -> tuple[list[Comunicado], list[str]]:
    """Devuelve (comunicados, avisos).

    1) Lee el listado de scjn.gob.mx para saber qué comunicados hay.
    2) Intenta abrir cada uno en internet2.scjn.gob.mx para sacar asuntos y votaciones.
       Si ese servidor bloquea la conexión, se reporta al menos número, tema y liga.
    Si el listado falla, prueba los id consecutivos directamente.
    """
    s = nueva_sesion()
    avisos: list[str] = []
    try:
        listado = leer_listado(s, ultimo_id)[:max_nuevos]
    except Exception as e:  # noqa: BLE001
        avisos.append(f"listado de scjn.gob.mx no disponible ({e}); se prueban id consecutivos")
        listado = None

    if listado is not None:
        resultado, bloqueado = [], False
        for f in listado:
            c = None
            if not bloqueado:
                try:
                    r = s.get(URL.format(id=f["id"]), timeout=30, headers=CABECERAS)
                    r.raise_for_status()
                    r.encoding = r.apparent_encoding or "windows-1252"
                    c = parsear(r.text, f["id"])
                except Exception as e:  # noqa: BLE001
                    bloqueado = True  # no insistir con el resto
                    avisos.append(f"el texto completo de los comunicados no se pudo abrir ({e}); se muestran solo número y tema")
                pausa(1)
            resultado.append(c or Comunicado(id=f["id"], numero=f["numero"], fecha="", titulo=f["titulo"]))
        return resultado, avisos

    nuevos: list[Comunicado] = []
    vacios = 0
    id_ = ultimo_id + 1
    while vacios < max_vacios and len(nuevos) < max_nuevos:
        r = s.get(URL.format(id=id_), timeout=30, headers=CABECERAS)
        if r.status_code == 404:
            c = None
        else:
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "windows-1252"  # sitio ASP clásico
            c = parsear(r.text, id_)
        if c:
            nuevos.append(c)
            vacios = 0
        else:
            vacios += 1
        id_ += 1
        pausa(1)
    return nuevos, avisos
