"""Genera la página-archivo (carpeta docs/) a partir de data/historico/.

Salida:
  docs/index.html            la página (se copia de monitor/plantilla_pagina.html)
  docs/datos/AAAA-MM.js      registros de cada mes  -> DATOS.push(...)
  docs/datos/indice.js       lista de meses y fecha de actualización

Se usan archivos .js (no .json) para que la página funcione tanto en GitHub
Pages como abriendo index.html directamente desde tu computadora.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

from .materias import anotar, normalizar

RAIZ = Path(__file__).resolve().parent.parent
HISTORICO = RAIZ / "data" / "historico"
PLANTILLA = Path(__file__).resolve().parent / "plantilla_pagina.html"
MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}


def carpeta_salida() -> Path:
    """docs/ en la raíz del repositorio (GitHub Pages solo publica desde ahí)."""
    base = os.getenv("GITHUB_WORKSPACE")
    if base:
        return Path(base) / "docs"
    raiz = RAIZ
    for p in [RAIZ, *RAIZ.parents]:
        if (p / ".git").exists():
            raiz = p
            break
    return raiz / "docs"


def iso(texto: str, respaldo: str = "") -> str:
    t = texto or ""
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", t, re.I)
    if m and m.group(2).lower() in MESES:
        return f"{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", t)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return m.group(0)
    return respaldo


def clave_asunto(tipo: str, numero: str) -> str:
    """Identificador para seguir un asunto entre la agenda y las sesiones."""
    t = normalizar(tipo)
    t = re.sub(r"\bacciones\b", "accion", t)
    t = re.sub(r"\bcontroversias\b", "controversia", t)
    num = re.match(r"\d+/\d{4}(?:-[a-z]+)?", normalizar(numero))
    return f"{t}|{num.group(0) if num else normalizar(numero)}"


def _resumen(texto: str, n: int = 260, tipo: str = "") -> str:
    texto = re.sub(r"\s+", " ", texto or "").strip()
    if tipo and texto.upper().startswith(tipo.upper()):
        texto = texto[len(tipo):].strip(" ,.")
    if texto.isupper():
        texto = texto.lower()
    texto = texto[:1].upper() + texto[1:]
    return texto[:n] + ("…" if len(texto) > n else "")


def registros_de_dia(dia: str, nov: dict) -> tuple[list[dict], list[dict]]:
    """Convierte lo guardado un día en registros uniformes. Devuelve (registros, sesiones)."""
    anotar(nov)
    regs: list[dict] = []
    sesiones: list[dict] = []

    for ses in nov.get("sesiones", []):
        f = iso(ses.get("fecha", ""), dia)
        sid = f"ses-{f}"
        sesiones.append({"id": sid, "fecha": f, "url": ses["url"], "votaciones": ses.get("votaciones", []),
                         "votos": ses.get("votos_anunciados", []), "decisiones": ses.get("decisiones", []),
                         "n": len(ses.get("asuntos", []))})
        for a in ses.get("asuntos", []):
            regs.append({"id": f"{sid}-{a['numero']}", "f": "sesion", "fecha": f, "tipo": a["tipo"],
                         "numero": a["numero"], "ponente": a.get("ponente", ""), "estado": a.get("estado", ""),
                         "titulo": f"{a['tipo']} {a['numero']}", "texto": _resumen(a.get("descripcion", ""), 600, a["tipo"]),
                         "materias": a.get("materias", []), "tramite": a.get("tramite", False),
                         "url": ses["url"], "sesion": sid, "clave": clave_asunto(a["tipo"], a["numero"])})

    for lista in nov.get("agenda", []):
        f = iso(lista.get("fecha", ""), dia)
        for a in lista.get("asuntos", []):
            regs.append({"id": f"ag-{f}-{a['numero']}", "f": "agenda", "fecha": f, "tipo": a["tipo"],
                         "numero": a["numero"], "ponente": a.get("ponente", ""), "orden": a.get("orden"),
                         "titulo": f"{a['tipo']} {a['numero']}", "texto": _resumen(a.get("descripcion", ""), 600),
                         "materias": a.get("materias", []), "tramite": a.get("tramite", False),
                         "url": lista["url"], "proyecto": a.get("proyecto", ""),
                         "desde": a.get("listado_desde", ""), "historial": a.get("historial", []),
                         "clave": clave_asunto(a["tipo"], a["numero"])})

    for t in nov.get("tesis", []):
        regs.append({"id": f"tesis-{t['registro']}", "f": "tesis", "fecha": iso(t.get("fecha_publicacion", ""), dia),
                     "tipo": t["tipo"], "numero": t.get("clave", ""), "instancia": t.get("instancia", ""),
                     "titulo": t.get("clave") or f"Registro {t['registro']}", "texto": t.get("rubro", ""),
                     "cuerpo": _resumen(t.get("texto", ""), 2500), "precedente": t.get("precedentes", ""),
                     "materias": t.get("materias_lista", []), "url": t.get("url", ""),
                     "alertas": t.get("alertas_vigencia", []), "contradiccion": t.get("contradiccion", False),
                     "referencias": t.get("referencias", []),
                     "votos": [{"d": v.get("descripcion", ""), "u": v.get("url", "")} for v in t.get("votos_detalle", [])],
                     "scjn": (t.get("instancia", "").lower() == "pleno" or "suprema corte" in t.get("instancia", "").lower())})

    for n in nov.get("dof", []):
        regs.append({"id": f"dof-{n['codigo']}", "f": "dof", "fecha": iso(n.get("fecha", ""), dia),
                     "tipo": n.get("categoria_etiqueta", ""), "titulo": n.get("titulo", ""),
                     "texto": n.get("organismo") or n.get("poder", ""), "materias": n.get("materias", []),
                     "url": n.get("url", ""), "prioridad": n.get("prioridad", 4), "edicion": n.get("edicion", "")})

    for c in nov.get("comunicados", []):
        regs.append({"id": f"com-{c['id']}", "f": "comunicado", "fecha": iso(c.get("fecha", ""), dia),
                     "tipo": "Comunicado", "numero": c.get("numero", ""),
                     "titulo": f"Comunicado {c.get('numero', '')}", "texto": c.get("titulo", ""),
                     "materias": [], "url": c.get("url", ""),
                     "asuntos": [a.get("asunto", "") for a in c.get("asuntos", [])]})
    return regs, sesiones


def construir(salida: Path | None = None, historico: Path = HISTORICO) -> Path:
    salida = salida or carpeta_salida()
    (salida / "datos").mkdir(parents=True, exist_ok=True)
    por_id: dict[str, dict] = {}
    sesiones: dict[str, dict] = {}
    for archivo in sorted(historico.glob("*.json")):
        dia = archivo.stem
        nov = json.loads(archivo.read_text(encoding="utf-8"))
        regs, ses = registros_de_dia(dia, nov)
        for r in regs:
            por_id[r["id"]] = r  # si algo se repite, gana la versión más reciente
        for s in ses:
            sesiones[s["id"]] = s

    por_mes: dict[str, dict] = defaultdict(lambda: {"registros": [], "sesiones": []})
    for r in por_id.values():
        por_mes[r["fecha"][:7] or "sin-fecha"]["registros"].append(r)
    for s in sesiones.values():
        por_mes[s["fecha"][:7]]["sesiones"].append(s)

    viejos = {p.name for p in (salida / "datos").glob("*.js")}
    for mes, contenido in por_mes.items():
        contenido["registros"].sort(key=lambda r: r["fecha"], reverse=True)
        js = "DATOS.push(" + json.dumps(contenido, ensure_ascii=False, separators=(",", ":")) + ");\n"
        (salida / "datos" / f"{mes}.js").write_text(js, encoding="utf-8")
        viejos.discard(f"{mes}.js")
    for v in viejos - {"indice.js"}:
        (salida / "datos" / v).unlink()

    indice = {"meses": sorted(por_mes, reverse=True),
              "actualizado": dt.datetime.now(dt.timezone(dt.timedelta(hours=-6))).strftime("%d/%m/%Y %H:%M"),
              "total": len(por_id)}
    (salida / "datos" / "indice.js").write_text("var INDICE = " + json.dumps(indice, ensure_ascii=False) + ";\n",
                                                encoding="utf-8")
    shutil.copyfile(PLANTILLA, salida / "index.html")
    (salida / ".nojekyll").write_text("")
    return salida
