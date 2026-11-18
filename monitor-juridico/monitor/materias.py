"""Clasificación por materia con palabras clave (sin IA).

Un asunto puede tener varias materias. Las palabras se buscan sin acentos y en
minúsculas sobre el tipo y la descripción del asunto (o el título de la nota del
DOF, o rubro + materias de la tesis). Puedes ajustar las listas aquí mismo.
"""
from __future__ import annotations

import re
import unicodedata

MATERIAS: dict[str, list[str]] = {
    "Constitucional": ["constitucion politica", "accion de inconstitucionalidad", "acciones de inconstitucionalidad",
                       "controversia constitucional", "declaratoria general", "reforma constitucional"],
    "Derechos humanos": ["derechos humanos", "igualdad", "discriminacion", "perspectiva de genero", "genero",
                         "indigena*", "afromexican*", "discapacidad", "nina*", "nino*", "infancia", "adolescente*",
                         "personas mayores", "libertad de expresion", "privacidad", "datos personales",
                         "tortura", "desaparicion", "migrante*", "medio ambiente", "derecho al agua"],
    "Penal": ["penal*", "delito*", "procedimientos penales", "prision", "vinculacion a proceso", "orden de aprehension",
              "victima*", "fiscalia", "ministerio publico", "cateo", "narcomenudeo", "ejecucion penal"],
    "Civil y familiar": ["civil", "familiar", "arrendamiento", "sucesion", "intestament*", "testament*", "filiacion",
                         "matrimonio", "divorcio", "alimentos", "patria potestad", "guarda y custodia",
                         "condomin*", "dano moral", "responsabilidad civil", "propiedad"],
    "Mercantil": ["mercantil", "concurso mercantil", "sociedad mercantil", "sociedades mercantiles", "titulos de credito",
                  "comercio", "usuarios de servicios financieros", "condusef", "bancari*", "afore"],
    "Laboral y seguridad social": ["trabajo", "laboral", "trabajador*", "seguro social", "imss",
                                   "issste", "pension*", "jubila*", "salario*", "conciliacion y arbitraje", "sindica*"],
    "Administrativa": ["administrativ*", "responsabilidades administrativas", "servidores publicos", "transparencia",
                       "acceso a la informacion", "contratacion publica", "licitacion", "seguridad publica"],
    "Fiscal": ["fiscal", "ley de ingresos", "impuesto*", "contribucion*", "tributari*", "derechos por", "servicio de administracion tributaria", "devolucion", "cuotas compensatorias", "aduan*", "predial"],
    "Electoral": ["electoral*", "partido politico", "partidos politicos", "candidatura", "proceso electoral",
                  "instituto electoral", "procesos electorales", "representacion proporcional"],
    "Competencia y telecomunicaciones": ["competencia economica", "telecomunicaciones", "radiodifusion",
                                         "practicas monopolicas", "espectro"],
    "Municipal y federalismo": ["municipio*", "ayuntamiento*", "invasion de esferas", "hacienda municipal",
                                "autonomia municipal", "coordinacion fiscal"],
}

# Asuntos de trámite: en el correo compacto se agrupan en una sola línea.
TRAMITE = re.compile(
    r"^(recurso de reclamacion|solicitud de ejercicio de la facultad de atraccion|solicitud de reasuncion|"
    r"queja|recurso de queja|incidente de inejecucion|incidente de|impedimento|recurso de inconformidad|"
    r"varios|aclaracion de sentencia|cumplimiento)", re.I)
_LEY_INGRESOS = re.compile(r"ley(?:es)? (?:numero \d+ )?de ingresos", re.I)


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).lower()


def _patron(palabra: str) -> str:
    """'penal*' = prefijo (penal, penales…); sin asterisco = palabra completa."""
    if palabra.endswith("*"):
        return r"\b" + re.escape(normalizar(palabra[:-1]).strip())
    return r"\b" + re.escape(normalizar(palabra).strip()) + r"\b"


_PATRONES = {m: re.compile("|".join(_patron(p) for p in ps), re.I) for m, ps in MATERIAS.items()}


def clasificar(*textos: str) -> list[str]:
    t = normalizar(" ".join(x for x in textos if x))
    return [m for m, p in _PATRONES.items() if p.search(t)]


def es_tramite(tipo: str, descripcion: str = "") -> bool:
    """Reclamaciones, atracciones, quejas, incidentes… y controversias por leyes de ingresos municipales."""
    t = normalizar(tipo)
    if TRAMITE.match(t):
        return True
    return t.startswith("controversia constitucional") and bool(_LEY_INGRESOS.search(normalizar(descripcion)))


def de_interes(materias: list[str], interes: list[str]) -> bool:
    if not interes:
        return True
    elegidas = {normalizar(i) for i in interes}
    return any(normalizar(m) in elegidas for m in materias)


_SJF = {"constitucional": "Constitucional", "penal": "Penal", "civil": "Civil y familiar",
        "laboral": "Laboral y seguridad social", "trabajo": "Laboral y seguridad social",
        "administrativa": "Administrativa", "electoral": "Electoral", "mercantil": "Mercantil",
        "familiar": "Civil y familiar", "fiscal": "Fiscal"}


def anotar(nov: dict) -> None:
    """Agrega 'materias' (y 'tramite' en asuntos del Pleno) a todo lo detectado."""
    for n in nov.get("dof", []):
        n["materias"] = clasificar(n.get("titulo", ""))
    for t in nov.get("tesis", []):
        propias = [_SJF[w] for w in normalizar(t.get("materias", "")).replace(",", " ").split() if w in _SJF]
        t["materias_lista"] = list(dict.fromkeys(propias + clasificar(t.get("rubro", ""))))
    for grupo in ("sesiones", "agenda"):
        for doc in nov.get(grupo, []):
            for a in doc.get("asuntos", []):
                a["materias"] = clasificar(a.get("tipo", ""), a.get("descripcion", ""))
                a["tramite"] = es_tramite(a.get("tipo", ""), a.get("descripcion", ""))
