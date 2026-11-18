"""Memoria del programa entre ejecuciones (archivos JSON dentro de data/).

- data/estado.json      → qué ya se vio (para avisar solo de lo nuevo)
- data/historico/AAAA-MM-DD.json → todo lo nuevo detectado ese día
  (sirve para el resumen semanal y, más adelante, para la página web)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
HISTORICO = DATA / "historico"
ARCHIVO = DATA / "estado.json"

VACIO = {
    "dof_codigos": [],
    "dof_ultima_fecha": None,
    "sjf_registros": [],
    "sjf_inicializado": False,
    "comunicados_ultimo_id": None,
    "sesiones_vistas": [],
    "agenda_vista": {},  # fecha ISO de la sesión -> URL de la lista ya enviada
}


def cargar() -> dict:
    if ARCHIVO.exists():
        return {**VACIO, **json.loads(ARCHIVO.read_text(encoding="utf-8"))}
    return dict(VACIO)


def guardar(estado: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    # se recortan las listas para que el archivo no crezca sin límite
    estado["dof_codigos"] = sorted(set(estado["dof_codigos"]))[-20000:]
    estado["sjf_registros"] = sorted(set(estado["sjf_registros"]))
    estado["sesiones_vistas"] = list(dict.fromkeys(estado.get("sesiones_vistas", [])))[-400:]
    estado["agenda_vista"] = dict(sorted(estado.get("agenda_vista", {}).items())[-60:])
    ARCHIVO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")


def guardar_historico(fecha: dt.date, novedades: dict) -> Path:
    HISTORICO.mkdir(parents=True, exist_ok=True)
    ruta = HISTORICO / f"{fecha.isoformat()}.json"
    previo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    for clave, lista in novedades.items():
        if isinstance(lista, list):
            previo.setdefault(clave, []).extend(lista)
    ruta.write_text(json.dumps(previo, ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def leer_historico(desde: dt.date, hasta: dt.date) -> dict:
    junto: dict = {"dof": [], "tesis": [], "comunicados": [], "sesiones": []}
    d = desde
    while d <= hasta:
        ruta = HISTORICO / f"{d.isoformat()}.json"
        if ruta.exists():
            for clave, lista in json.loads(ruta.read_text(encoding="utf-8")).items():
                junto.setdefault(clave, []).extend(lista)
        d += dt.timedelta(days=1)
    return junto
