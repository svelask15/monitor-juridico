"""Arma el boletín (Markdown para archivo/Telegram y HTML para correo)."""
from __future__ import annotations

import html
from collections import defaultdict

from .clasificar import CATEGORIAS


def _orden_dof(notas: list[dict], prioridad_max: int):
    grupos: dict[str, list[dict]] = defaultdict(list)
    for n in notas:
        if n["prioridad"] <= prioridad_max:
            grupos[n["categoria"]].append(n)
    for clave, (etiqueta, _) in sorted(CATEGORIAS.items(), key=lambda kv: kv[1][1]):
        if grupos.get(clave):
            yield etiqueta, sorted(grupos[clave], key=lambda n: (n["fecha"][-4:], n["fecha"][3:5], n["fecha"][:2]))


def hay_algo(nov: dict, prioridad_max: int) -> bool:
    return bool(
        nov.get("comunicados") or nov.get("tesis")
        or any(n["prioridad"] <= prioridad_max for n in nov.get("dof", []))
    )


def markdown(titulo: str, nov: dict, prioridad_max: int = 2, errores: list[str] | None = None) -> str:
    L = [f"# {titulo}", ""]
    tesis = nov.get("tesis", [])
    alertas = [t for t in tesis if t.get("alertas_vigencia")]
    com = nov.get("comunicados", [])
    dof = [n for n in nov.get("dof", []) if n["prioridad"] <= prioridad_max]
    L.append(f"**Resumen:** {len(com)} comunicados del Pleno · {len(tesis)} tesis nuevas "
             f"({sum(t['tipo'] == 'Jurisprudencia' for t in tesis)} jurisprudencias) · "
             f"{len(alertas)} posibles cambios de vigencia · {len(dof)} publicaciones relevantes en el DOF")
    L.append("")

    if alertas:
        L += ["## ⚠️ Criterios que podrían haber dejado de estar vigentes", "",
              "_Detectado por palabras clave: verifica en el Semanario._", ""]
        for t in alertas:
            L.append(f"- **{t['clave'] or t['registro']}** — {t['rubro'][:220]}  ")
            L.append(f"  {'; '.join(t['alertas_vigencia'])} · [registro {t['registro']}]({t['url']})")
        L.append("")

    if com:
        L += ["## 🏛️ Lo que resolvió el Pleno de la SCJN", ""]
        for c in com:
            L.append(f"### Comunicado {c['numero']}" + (f" · {c['fecha']}" if c["fecha"] else ""))
            if c["titulo"]:
                L.append(f"**{c['titulo']}**  ")
            if c["resumen"]:
                L.append(c["resumen"])
            for a in c["asuntos"]:
                L.append(f"- {a['asunto']}" + (f" (sesión {a['sesion']})" if a["sesion"] else ""))
            if c["votaciones"]:
                L.append(f"- _Votaciones mencionadas:_ {'; '.join(c['votaciones'])}")
            L.append(f"[Leer comunicado]({c['url']})")
            L.append("")

    if tesis:
        L += ["## 📚 Tesis y jurisprudencia nuevas (Semanario Judicial)", ""]
        for tipo in ("Jurisprudencia", "Tesis aislada"):
            grupo = [t for t in tesis if t["tipo"] == tipo]
            if not grupo:
                continue
            L.append(f"### {tipo} ({len(grupo)})")
            for t in grupo:
                extra = " · ".join(x for x in (t["instancia"], t["materias"], t["fecha_publicacion"]) if x)
                L.append(f"- **{t['clave'] or 'Sin clave'}** — {t['rubro'][:300]}  ")
                L.append(f"  {extra} · [registro {t['registro']}]({t['url']})")
                if t.get("precedentes"):
                    L.append(f"  _Precedente:_ {t['precedentes'][:250]}")
                if t.get("votos"):
                    L.append(f"  _Votos:_ {'; '.join(t['votos'])[:250]}")
            L.append("")

    if dof:
        L += ["## 📰 Diario Oficial de la Federación", ""]
        for etiqueta, notas in _orden_dof(dof, prioridad_max):
            L.append(f"### {etiqueta} ({len(notas)})")
            for n in notas:
                kw = f" 🔎 _{', '.join(n['palabras_clave'])}_" if n["palabras_clave"] else ""
                titulo = n["titulo"] or "(SIDOF no dio título)"
                L.append(f"- {n['fecha']} · [{titulo[:300]}]({n['url']}) — {n['organismo'] or n['poder']}{kw}")
            L.append("")

    if errores:
        L += ["## ❗ Fuentes con problemas", ""] + [f"- {e}" for e in errores] + [""]
    if not hay_algo(nov, prioridad_max) and not errores:
        L.append("Sin novedades relevantes.")
    return "\n".join(L)


def html_desde_markdown(md: str) -> str:
    """Conversión mínima suficiente para el correo (sin dependencias)."""
    import re

    def inline(t: str) -> str:
        t = html.escape(t, quote=False)
        t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"(?<![\w*])_(.+?)_(?!\w)", r"<i>\1</i>", t)
        return t

    out, en_lista = [], False
    for linea in md.splitlines():
        crudo = linea.rstrip()
        if crudo.startswith("- "):
            if not en_lista:
                out.append("<ul>")
                en_lista = True
            out.append(f"<li>{inline(crudo[2:])}")
            continue
        if crudo.startswith("  ") and en_lista:
            out.append(f"<br>{inline(crudo.strip())}")
            continue
        if en_lista:
            out.append("</ul>")
            en_lista = False
        if crudo.startswith("### "):
            out.append(f"<h3>{inline(crudo[4:])}</h3>")
        elif crudo.startswith("## "):
            out.append(f"<h2>{inline(crudo[3:])}</h2>")
        elif crudo.startswith("# "):
            out.append(f"<h1>{inline(crudo[2:])}</h1>")
        elif crudo:
            out.append(f"<p>{inline(crudo)}</p>")
    if en_lista:
        out.append("</ul>")
    estilo = ("body{font-family:Georgia,serif;max-width:760px;margin:auto;color:#222;line-height:1.45}"
              "h1{color:#5b1f2e}h2{border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:28px}"
              "h3{color:#444;margin-bottom:4px}li{margin-bottom:8px}a{color:#1a4f8b}")
    return f"<html><head><meta charset='utf-8'><style>{estilo}</style></head><body>{''.join(out)}</body></html>"
