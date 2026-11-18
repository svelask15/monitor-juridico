"""Diario Oficial de la Federación vía el servicio oficial SIDOF (JSON).

Endpoint diario: https://sidof.segob.gob.mx/dof/sidof/notas/DD-MM-AAAA
Devuelve las notas de la edición matutina, vespertina y extraordinaria.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict

from .http import nueva_sesion, pausa

BASES = (
    "https://sidof.segob.gob.mx/dof/sidof",
    "https://sidofqa.segob.gob.mx/dof/sidof",  # respaldo
)
EDICIONES = {
    "NotasMatutinas": "Matutina",
    "NotasVespertinas": "Vespertina",
    "NotasExtraordinarias": "Extraordinaria",
}


@dataclass
class NotaDOF:
    codigo: int
    fecha: str  # DD-MM-AAAA
    edicion: str
    titulo: str
    poder: str  # p. ej. PODER EJECUTIVO, PODER JUDICIAL
    organismo: str  # p. ej. SUPREMA CORTE DE JUSTICIA DE LA NACION
    pagina: int | None
    url: str

    def dict(self) -> dict:
        return asdict(self)


def url_nota(codigo: int, fecha_ddmmaaaa: str) -> str:
    return f"https://dof.gob.mx/nota_detalle.php?codigo={codigo}&fecha={fecha_ddmmaaaa.replace('-', '/')}"


def parsear_dia(data: dict) -> list[NotaDOF]:
    """Convierte la respuesta JSON de SIDOF en una lista de notas."""
    notas: list[NotaDOF] = []
    for clave, edicion in EDICIONES.items():
        for n in data.get(clave) or []:
            codigo = n.get("codNota")
            if not codigo:
                continue
            fecha = n.get("fecha", "")
            notas.append(
                NotaDOF(
                    codigo=int(codigo),
                    fecha=fecha,
                    edicion=edicion,
                    titulo=(n.get("titulo") or "").strip(),
                    poder=(n.get("nombreCodOrgaUno") or "").strip(),
                    organismo=(n.get("codOrgaDos") or "").strip(),
                    pagina=n.get("pagina"),
                    url=url_nota(int(codigo), fecha),
                )
            )
    return notas


def obtener_dia(fecha: dt.date, sesion=None) -> list[NotaDOF]:
    s = sesion or nueva_sesion()
    f = fecha.strftime("%d-%m-%Y")
    errores: list[str] = []
    for base in BASES:
        try:
            r = s.get(f"{base}/notas/{f}", timeout=30, headers={"Accept": "*/*"})
            r.raise_for_status()
            data = r.json()
            if data.get("messageCode") not in (200, "200", None):
                raise RuntimeError(f"SIDOF respondió {data.get('messageCode')}: {data.get('response')}")
            return parsear_dia(data)
        except Exception as e:  # noqa: BLE001 — probamos el respaldo
            errores.append(f"{base.split('/')[2]}: {e}")
            pausa(2)
    raise RuntimeError(f"No se pudo leer el DOF del {f} → " + " | ".join(errores))


def obtener_rango(desde: dt.date, hasta: dt.date) -> list[NotaDOF]:
    s = nueva_sesion()
    notas: list[NotaDOF] = []
    d = desde
    while d <= hasta:  # incluye fines de semana: puede haber ediciones extraordinarias
        notas.extend(obtener_dia(d, s))
        pausa(1)
        d += dt.timedelta(days=1)
    return notas
