"""Clasificación de notas del DOF con reglas fijas (expresiones regulares, sin IA).

El orden importa: se asigna la primera categoría que coincida.
"""
from __future__ import annotations

import re
import unicodedata

from .dof import NotaDOF


def normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).lower().strip()


# (clave, etiqueta para el reporte, prioridad: 1 = lo más importante)
CATEGORIAS = {
    "constitucion": ("Reformas a la Constitución", 1),
    "scjn_sentencia": ("SCJN: sentencias y votos publicados", 1),
    "ley_nueva": ("Leyes y códigos nuevos", 1),
    "reforma_legal": ("Reformas, adiciones y derogaciones legales", 1),
    "scjn_acuerdo": ("SCJN: acuerdos generales y avisos", 2),
    "judicial": ("Otros órganos del Poder Judicial", 2),
    "reglamento": ("Reglamentos", 2),
    "decreto": ("Otros decretos", 3),
    "acuerdo": ("Acuerdos, lineamientos y disposiciones generales", 3),
    "otros": ("Otros", 4),
}

_R = lambda p: re.compile(p, re.I)  # noqa: E731

REGLAS = [
    ("constitucion", lambda t, n: _R(r"decreto por el que se (reforma|adiciona|deroga).*constitucion politica de los estados unidos mexicanos").search(t)),
    ("scjn_sentencia", lambda t, n: "suprema corte" in n and _R(r"sentencia|voto|accion(es)? de inconstitucionalidad|controversia(s)? constitucional|declaratoria general").search(t)),
    ("scjn_acuerdo", lambda t, n: "suprema corte" in n),
    ("ley_nueva", lambda t, n: _R(r"decreto por el que se expide|^ley |^codigo ").search(t)),
    ("reforma_legal", lambda t, n: _R(r"decreto por el que se (reforma|adiciona|deroga|abroga)").search(t)),
    ("judicial", lambda t, n: _R(r"poder judicial|organo de administracion judicial|tribunal de disciplina|tribunal electoral|consejo de la judicatura").search(n)),
    ("reglamento", lambda t, n: _R(r"\breglamento\b").search(t)),
    ("decreto", lambda t, n: t.startswith("decreto")),
    ("acuerdo", lambda t, n: _R(r"^(acuerdo|lineamientos|disposiciones|reglas|resolucion)").search(t)),
]


def clasificar(nota: NotaDOF, palabras_clave: list[str] | None = None) -> dict:
    t = normalizar(nota.titulo)
    n = normalizar(f"{nota.poder} {nota.organismo}")
    categoria = "otros"
    for clave, regla in REGLAS:
        if regla(t, n):
            categoria = clave
            break
    coincidencias = [p for p in (palabras_clave or []) if normalizar(p) in t]
    etiqueta, prioridad = CATEGORIAS[categoria]
    if coincidencias and prioridad > 2:
        prioridad = 2  # una palabra clave tuya sube la nota de nivel
    return {
        **nota.dict(),
        "categoria": categoria,
        "categoria_etiqueta": etiqueta,
        "prioridad": prioridad,
        "palabras_clave": coincidencias,
    }
