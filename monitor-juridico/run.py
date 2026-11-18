#!/usr/bin/env python3
"""Monitor jurídico: SCJN, Semanario Judicial y DOF.

Uso:
  python run.py                 # revisión diaria (avisa solo de lo nuevo)
  python run.py --semanal       # resumen de los últimos 7 días
  python run.py --sin-enviar    # genera el reporte sin mandar correo/Telegram
  python run.py --solo dof      # revisa solo una fuente (dof, semanario, comunicados)
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import traceback
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from monitor import comunicados, dof, estado, notificar, reporte, sjf
from monitor.clasificar import clasificar

RAIZ = Path(__file__).resolve().parent
REPORTES = RAIZ / "reportes"
TZ = ZoneInfo("America/Mexico_City")
MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(TZ):%H:%M:%S}] {msg}", flush=True)


def fecha_es(texto: str) -> dt.date | None:
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", texto or "", re.I)
    if not m or m.group(2).lower() not in MESES:
        return None
    return dt.date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))


# ------------------------------------------------------------------ fuentes
def revisar_dof(cfg, est, hoy, nov):
    c = cfg["dof"]
    if est["dof_ultima_fecha"]:
        desde = dt.date.fromisoformat(est["dof_ultima_fecha"]) - dt.timedelta(days=1)
    else:
        desde = hoy - dt.timedelta(days=c.get("dias_iniciales", 3))
    notas = list({n.codigo: n for n in dof.obtener_rango(desde, hoy)}.values())
    vistos = set(est["dof_codigos"])
    nuevas = [n for n in notas if n.codigo not in vistos]
    nov["dof"] = [clasificar(n, c.get("palabras_clave")) for n in nuevas]
    est["dof_codigos"].extend(n.codigo for n in nuevas)
    est["dof_ultima_fecha"] = hoy.isoformat()
    log(f"DOF: {len(notas)} notas revisadas del {desde} al {hoy}, {len(nuevas)} nuevas")


def revisar_semanario(cfg, est, hoy, nov):
    c = cfg["semanario"]
    cli = sjf.ClienteSJF()
    todas = cli.listar(c.get("epocas", ["210"]))
    vistos = set(est["sjf_registros"])
    nuevas = [t for t in todas if t.registro not in vistos]
    est["sjf_registros"].extend(t.registro for t in todas)

    relevantes = [t for t in nuevas if sjf.instancia_permitida(t, c.get("instancias", []))]
    if not est["sjf_inicializado"]:
        # primera vez: todo es "nuevo"; se muestran solo las más recientes como muestra
        relevantes = sorted(relevantes, key=lambda t: t.registro, reverse=True)[: c.get("mostrar_al_iniciar", 15)]
        est["sjf_inicializado"] = True
        log(f"Semanario: base inicial con {len(todas)} tesis")

    completas = []
    for i, t in enumerate(sorted(relevantes, key=lambda t: t.registro)):
        if i < c.get("max_detalles", 80):
            try:
                t = cli.detalle(t.registro) or t
            except Exception as e:  # noqa: BLE001
                log(f"  sin detalle para {t.registro}: {e}")
        t.alertas_vigencia = sjf.detectar_cambios_vigencia(t)
        for id_voto in t.votos[:4]:
            try:
                t.votos_detalle.append(cli.voto(int(id_voto)) if str(id_voto).isdigit()
                                       else {"id": id_voto, "url": t.url, "descripcion": id_voto})
            except Exception as e:  # noqa: BLE001
                log(f"  sin detalle del voto {id_voto}: {e}")
        completas.append(t.dict())
    nov["tesis"] = completas
    from collections import Counter
    conteo = Counter(t.instancia or "(sin instancia)" for t in nuevas)
    nov["instancias"] = [f"{k}: {v}" for k, v in conteo.most_common()]
    log(f"Semanario: {len(todas)} tesis en la época, {len(nuevas)} nuevas, {len(completas)} reportadas")


def revisar_comunicados(cfg, est, hoy, nov):
    c = cfg["comunicados"]
    inicial = est["comunicados_ultimo_id"] is None
    ultimo = est["comunicados_ultimo_id"] or c.get("id_inicial", 8545)
    nuevos, avisos = comunicados.obtener_nuevos(ultimo)
    nov.setdefault("avisos", []).extend(f"Comunicados: {a}" for a in avisos)
    if nuevos:
        est["comunicados_ultimo_id"] = max(x.id for x in nuevos)
    elif inicial:
        est["comunicados_ultimo_id"] = ultimo
    if inicial:
        limite = hoy - dt.timedelta(days=c.get("dias_iniciales", 10))
        con_fecha = [x for x in nuevos if fecha_es(x.fecha)]
        if con_fecha:
            nuevos = [x for x in nuevos if (fecha_es(x.fecha) or hoy) >= limite]
        else:  # sin fechas (solo listado): mostrar los más recientes
            nuevos = nuevos[-c.get("mostrar_al_iniciar", 6):]
    nov["comunicados"] = [x.dict() for x in nuevos]
    log(f"Comunicados: {len(nuevos)} nuevos (último id {est['comunicados_ultimo_id']})")


FUENTES = {
    "dof": ("Diario Oficial (SIDOF)", revisar_dof),
    "semanario": ("Semanario Judicial de la Federación", revisar_semanario),
    "comunicados": ("Comunicados de prensa de la SCJN", revisar_comunicados),
}


# ------------------------------------------------------------------- flujo
def enviar(asunto, md, cfg, args, vacio):
    if args.sin_enviar or (vacio and not cfg["envio"].get("enviar_si_vacio")):
        log("No se envía notificación")
        return
    html = reporte.html_desde_markdown(md)
    for canal, fn in (("correo", lambda: notificar.correo(asunto, md, html)),
                      ("Telegram", lambda: notificar.telegram(md))):
        try:
            log(f"{canal}: {'enviado' if fn() else 'no configurado'}")
        except Exception as e:  # noqa: BLE001
            log(f"{canal}: ERROR {e}")


def diario(cfg, args) -> int:
    hoy = dt.datetime.now(TZ).date()
    est = estado.cargar()
    nov: dict = {"dof": [], "tesis": [], "comunicados": []}
    errores = []
    for clave, (nombre, fn) in FUENTES.items():
        if args.solo and clave not in args.solo:
            continue
        try:
            fn(cfg, est, hoy, nov)
        except Exception as e:  # noqa: BLE001 — una fuente caída no detiene las demás
            traceback.print_exc()
            errores.append(f"{nombre}: {type(e).__name__}: {str(e)[:200]}")

    pmax = cfg["dof"].get("prioridad_maxima", 2)
    nov_guardar = {k: v for k, v in nov.items() if k not in ("avisos", "instancias")}
    nov_guardar["dof"] = [n for n in nov["dof"] if n["prioridad"] <= pmax]
    estado.guardar_historico(hoy, nov_guardar)
    estado.guardar(est)

    titulo = f"Monitor jurídico — {hoy:%d/%m/%Y}"
    errores += nov.pop("avisos", [])
    md = reporte.markdown(titulo, nov, pmax, errores)
    REPORTES.mkdir(exist_ok=True)
    (REPORTES / f"{hoy.isoformat()}.md").write_text(md, encoding="utf-8")
    vacio = not reporte.hay_algo(nov, pmax) and not errores
    enviar(titulo, md, cfg, args, vacio)
    print("\n" + md)
    return 0


def semanal(cfg, args) -> int:
    hoy = dt.datetime.now(TZ).date()
    desde = hoy - dt.timedelta(days=6)
    nov = estado.leer_historico(desde, hoy)
    pmax = cfg["dof"].get("prioridad_maxima", 2)
    titulo = f"Resumen semanal — {desde:%d/%m} al {hoy:%d/%m/%Y}"
    md = reporte.markdown(titulo, nov, pmax)
    REPORTES.mkdir(exist_ok=True)
    (REPORTES / f"semana-{hoy.isoformat()}.md").write_text(md, encoding="utf-8")
    enviar(titulo, md, cfg, args, not reporte.hay_algo(nov, pmax))
    print("\n" + md)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--semanal", action="store_true", help="resumen de los últimos 7 días")
    p.add_argument("--sin-enviar", action="store_true", help="no mandar correo ni Telegram")
    p.add_argument("--solo", nargs="+", choices=list(FUENTES), help="revisar solo estas fuentes")
    args = p.parse_args()
    cfg = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    return semanal(cfg, args) if args.semanal else diario(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
