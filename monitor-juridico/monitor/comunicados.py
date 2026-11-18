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


def obtener_nuevos(ultimo_id: int, max_vacios: int = 4, max_nuevos: int = 60) -> list[Comunicado]:
    s = nueva_sesion()
    nuevos: list[Comunicado] = []
    vacios = 0
    id_ = ultimo_id + 1
    while vacios < max_vacios and len(nuevos) < max_nuevos:
        r = s.get(URL.format(id=id_), timeout=30)
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
    return nuevos
