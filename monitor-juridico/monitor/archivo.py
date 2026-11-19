"""Archivo histórico para la página (data/archivo/).

A diferencia de data/historico/ (lo nuevo de cada día, que alimenta el correo),
aquí se guarda todo lo disponible, aunque ya haya pasado:

  data/archivo/agenda/AAAA-MM-DD.json    cada lista oficial para sesión
  data/archivo/sesiones/AAAA-MM-DD.json  cada versión taquigráfica
  data/archivo/tesis.json                tesis de la SCJN + las que agregues por registro

Se rellena hacia atrás poco a poco (unos cuantos PDF por corrida) para no
saturar los servidores de la SCJN ni alargar la revisión diaria.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import agenda, sesiones
from .http import nueva_sesion, pausa

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "data" / "archivo"
TESIS = ARCHIVO / "tesis.json"
MANUAL = RAIZ / "tesis_por_registro.txt"


def _guardar(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def _leer(ruta: Path, defecto):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else defecto


# ------------------------------------------------------------- agenda y sesiones
def rellenar_agenda(paginas: int = 3, maximo: int = 8) -> int:
    """Descarga listas oficiales que aún no estén en el archivo (o que hayan cambiado)."""
    s = nueva_sesion()
    hechas = 0
    for pagina in range(paginas):
        r = s.get(agenda.LISTADO.format(pagina=pagina), timeout=30)
        r.raise_for_status()
        for fila in agenda.parsear_listado(r.text):
            if hechas >= maximo or not fila["iso"]:
                continue
            ruta = ARCHIVO / "agenda" / f"{fila['iso']}.json"
            if _leer(ruta, {}).get("url") == fila["url"]:
                continue
            pausa(1)
            pdf = s.get(fila["url"], timeout=90)
            pdf.raise_for_status()
            lista = agenda.parsear_lista(sesiones.texto_pdf(pdf.content), fila["url"], fila["fecha"],
                                         agenda.ligas_proyectos(pdf.content))
            _guardar(ruta, lista.dict())
            hechas += 1
        if hechas >= maximo:
            break
        pausa(1)
    return hechas


def rellenar_sesiones(paginas: int = 3, maximo: int = 6) -> int:
    s = nueva_sesion()
    hechas = 0
    for pagina in range(paginas):
        r = s.get(sesiones.LISTADO.format(pagina=pagina), timeout=30)
        r.raise_for_status()
        for fila in sesiones.parsear_listado(r.text):
            if hechas >= maximo or (fila.get("instancia") and fila["instancia"].lower() != "pleno"):
                continue
            iso = agenda.fecha_iso(fila["fecha"])
            if not iso:
                continue
            ruta = ARCHIVO / "sesiones" / f"{iso}.json"
            if ruta.exists():
                continue
            pausa(1)
            pdf = s.get(fila["url"], timeout=90)
            pdf.raise_for_status()
            _guardar(ruta, sesiones.parsear_sesion(sesiones.texto_pdf(pdf.content), fila["url"], fila["fecha"]).dict())
            hechas += 1
        if hechas >= maximo:
            break
        pausa(1)
    return hechas


def guardar_sesiones(lista: list[dict]) -> None:
    """Las sesiones que ya trajo la revisión diaria también van al archivo."""
    for ses in lista:
        iso = agenda.fecha_iso(ses.get("fecha", ""))
        if iso:
            _guardar(ARCHIVO / "sesiones" / f"{iso}.json", ses)


def guardar_listas(lista: list[dict]) -> None:
    for l in lista:
        iso = agenda.fecha_iso(l.get("fecha", ""))
        if iso:
            _guardar(ARCHIVO / "agenda" / f"{iso}.json", l)


# ------------------------------------------------------------------- tesis
def registros_manuales() -> list[int]:
    if not MANUAL.exists():
        return []
    numeros = []
    for linea in MANUAL.read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0]
        numeros += [int(n) for n in re.findall(r"\b\d{6,8}\b", linea)]
    return list(dict.fromkeys(numeros))


def actualizar_tesis(cli, todas, es_scjn, completas: list[dict], max_detalles: int = 25) -> dict:
    """Guarda en tesis.json: todas las tesis de la SCJN de la época vigente, las nuevas
    reportadas hoy (con detalle) y las que pediste por registro en tesis_por_registro.txt."""
    from . import sjf
    archivo: dict = _leer(TESIS, {})
    for t in todas:
        if es_scjn(t) and str(t.registro) not in archivo:
            t.alertas_vigencia = sjf.detectar_cambios_vigencia(t)
            archivo[str(t.registro)] = t.dict()
    for t in completas:
        archivo[str(t["registro"])] = {**archivo.get(str(t["registro"]), {}), **t}

    manuales = registros_manuales()
    pendientes = [r for r in manuales if not archivo.get(str(r), {}).get("texto")]
    pendientes += [int(r) for r, t in archivo.items() if not t.get("texto") and int(r) not in pendientes]
    hechas = 0
    for registro in pendientes:
        if hechas >= max_detalles:
            break
        try:
            t = cli.detalle(registro)
        except Exception:  # noqa: BLE001 — se reintenta en la siguiente corrida
            t = None
        hechas += 1
        if t:
            t.alertas_vigencia = sjf.detectar_cambios_vigencia(t)
            archivo[str(registro)] = {**archivo.get(str(registro), {}), **t.dict()}
        pausa(1)
    for r in manuales:
        if str(r) in archivo:
            archivo[str(r)]["agregada_por_ti"] = True
    _guardar(TESIS, archivo)
    return {"total": len(archivo), "detalles": hechas, "manuales": len(manuales)}


# ------------------------------------------------------- épocas anteriores
EPOCAS = {"200": "Undécima Época", "100": "Décima Época", "5": "Novena Época", "4": "Octava Época"}
MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}


def _fecha_aprox(doc: dict) -> str:
    """Fecha de publicación; en épocas viejas se toma el mes y año de la localización."""
    f = str(doc.get("fechaPublicacion") or "")
    if re.match(r"\d{4}-\d{2}-\d{2}", f):
        return f[:10]
    m = re.search(r"(\w+) de (\d{4})", str(doc.get("localizacion") or ""), re.I)
    if m and m.group(1).lower() in MESES:
        return f"{m.group(2)}-{MESES[m.group(1).lower()]:02d}-01"
    m = re.search(r"\b(19\d\d|20\d\d)\b", str(doc.get("localizacion") or ""))
    return f"{m.group(1)}-01-01" if m else ""


def compacta(doc: dict, epoca: str) -> dict:
    from . import sjf
    return {"registro": int(doc.get("ius") or doc.get("id") or 0),
            "clave": sjf.limpiar(doc.get("claveTesis")), "rubro": sjf.limpiar(doc.get("rubro")),
            "tipo": sjf._tipo(doc), "instancia": sjf.instancia_legible(doc), "epoca": EPOCAS.get(epoca, epoca),
            "fecha": _fecha_aprox(doc)}


def rellenar_epocas(cli, epocas: list[str] | None = None, paginas_por_corrida: int = 25, tam: int = 200) -> dict:
    """Avanza unas páginas por corrida en cada época hasta tener todas las tesis de la SCJN."""
    resumen = {}
    presupuesto = paginas_por_corrida
    for epoca in epocas or list(EPOCAS):
        ruta = ARCHIVO / "epocas" / f"{epoca}.json"
        datos = _leer(ruta, {"siguiente": 0, "total_paginas": None, "tesis": {}})
        if datos["total_paginas"] is not None and datos["siguiente"] >= datos["total_paginas"]:
            resumen[epoca] = f"completa ({len(datos['tesis'])})"
            continue
        while presupuesto > 0:
            docs, total = cli.pagina_scjn(epoca, datos["siguiente"], tam)
            datos["total_paginas"] = total
            for d in docs:
                c = compacta(d, epoca)
                if c["registro"]:
                    datos["tesis"][str(c["registro"])] = c
            datos["siguiente"] += 1
            presupuesto -= 1
            if not docs or datos["siguiente"] >= total:
                break
            pausa(1.5)
        _guardar(ruta, datos)
        resumen[epoca] = f"{len(datos['tesis'])} tesis, página {datos['siguiente']} de {datos['total_paginas']}"
        if presupuesto <= 0:
            break
    return resumen
