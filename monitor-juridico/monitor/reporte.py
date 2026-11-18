"""Arma el boletín (Markdown para archivo/Telegram y HTML para correo)."""
from __future__ import annotations

import html
import re
from collections import Counter, defaultdict

from .clasificar import CATEGORIAS
from .materias import de_interes

ABREV_ESTADO = {"Resueltos": "", "Quedaron en lista": "en lista", "Retirados": "retirado", "Aplazados": "aplazado"}


def _etiquetas(mats: list[str], op: dict) -> str:
    if not mats:
        return ""
    estrella = "★ " if op["interes"] and de_interes(mats, op["interes"]) else ""
    return f" {estrella}_[{', '.join(mats)}]_"


def _visible(mats: list[str], op: dict) -> bool:
    return op["modo"] != "filtrar" or de_interes(mats, op["interes"])


def _orden_interes(items: list[dict], op: dict, clave="materias"):
    if op["modo"] == "priorizar" and op["interes"]:
        return sorted(items, key=lambda a: not de_interes(a.get(clave, []), op["interes"]))
    return items


def _agrupado(asuntos: list[dict], con_estado: bool) -> list[str]:
    """'**Recurso de Reclamación (6):** 346/2026, 377/2026 (en lista)…'"""
    por_tipo: dict[str, list[str]] = defaultdict(list)
    for a in asuntos:
        etiqueta = ABREV_ESTADO.get(a.get("estado", ""), (a.get("estado") or "").lower()) if con_estado else ""
        por_tipo[a["tipo"] or "Otros"].append(a["numero"] + (f" ({etiqueta})" if etiqueta else ""))
    return [f"- **{t} ({len(n)}):** {', '.join(n)}" for t, n in sorted(por_tipo.items(), key=lambda kv: -len(kv[1]))]


def _desc(a: dict, n: int) -> str:
    d = a.get("descripcion", "")
    if d.upper().startswith((a.get("tipo") or "").upper()):
        d = d[len(a["tipo"]):].strip(" ,.")
    if d.isupper():
        d = d.lower()
    d = d[:n] + ("…" if len(d) > n else "")
    return d[:1].upper() + d[1:]


_TIPO_VOTO = re.compile(r"\bvotos? (concurrente|particular|aclaratorio|razonado|de minor[ií]a)", re.I)


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
        nov.get("comunicados") or nov.get("tesis") or nov.get("sesiones") or nov.get("agenda")
        or any(n["prioridad"] <= prioridad_max for n in nov.get("dof", []))
    )


def markdown(titulo: str, nov: dict, prioridad_max: int = 2, errores: list[str] | None = None,
             opciones: dict | None = None) -> str:
    op = {"formato": "completo", "interes": [], "modo": "priorizar", **(opciones or {})}
    L = [f"# {titulo}", ""]
    tesis = [t for t in nov.get("tesis", []) if _visible(t.get("materias_lista", []), op) or t.get("alertas_vigencia")]
    tesis = _orden_interes(tesis, op, "materias_lista")
    alertas = [t for t in tesis if t.get("alertas_vigencia")]
    com = nov.get("comunicados", [])
    dof = [n for n in nov.get("dof", []) if n["prioridad"] <= prioridad_max
           and (n["prioridad"] == 1 or _visible(n.get("materias", []), op))]
    ses_n = len(nov.get("sesiones", []))
    ag_n = len(nov.get("agenda", []))
    L.append(f"**Resumen:** {ses_n} sesiones del Pleno · {ag_n} listas para próximas sesiones · {len(com)} comunicados · {len(tesis)} tesis nuevas "
             f"({sum(t['tipo'] == 'Jurisprudencia' for t in tesis)} jurisprudencias, "
             f"{sum(bool(t.get('contradiccion')) for t in tesis)} por contradicción de criterios) · "
             f"{len(alertas)} alertas de vigencia · {len(dof)} publicaciones relevantes en el DOF")
    L.append("")

    if alertas:
        L += ["## ⚠️ Criterios que podrían haber dejado de estar vigentes", "",
              "_El texto de la tesis lo dice expresamente; verifica en el Semanario._", ""]
        for t in alertas:
            L.append(f"- **{t['clave'] or t['registro']}** — {t['rubro'][:220]}  ")
            refs = f" · cita: {', '.join(t.get('referencias', []))}" if t.get("referencias") else ""
            L.append(f"  {'; '.join(t['alertas_vigencia'])}{refs} · [registro {t['registro']}]({t['url']})")
        L.append("")

    if com:
        L += ["## 🏛️ Lo que resolvió el Pleno de la SCJN", ""]
        for c in sorted(com, key=lambda c: c["id"], reverse=True):
            L.append(f"### Comunicado {c['numero']}" + (f" · {c['fecha']}" if c["fecha"] else ""))
            if c["titulo"]:
                L.append(f"**{c['titulo']}**  ")
            if c["resumen"]:
                L.append(c["resumen"])
            for a_ in c["asuntos"]:
                L.append(f"- {a_['asunto']}" + (f" (sesión {a_['sesion']})" if a_["sesion"] else ""))
            if c["votaciones"]:
                L.append(f"- _Votaciones mencionadas:_ {'; '.join(c['votaciones'])}")
            L.append(f"[Leer comunicado]({c['url']})")
            L.append("")

    for ses in nov.get("sesiones", []):
        L += [f"## 🎙️ Sesión del Pleno · {ses['fecha']}", f"[Versión taquigráfica (PDF)]({ses['url']})", ""]
        asuntos = ses["asuntos"]
        if op["formato"] == "compacto":
            conteo = Counter(a_["estado"] or "Sin estado" for a_ in asuntos)
            L.append(" · ".join(f"{e} {n}" for e, n in sorted(conteo.items(), key=lambda kv: kv[0] != "Resueltos")))
            L.append("")
            destacados = [a_ for a_ in asuntos if not a_.get("tramite") and _visible(a_.get("materias", []), op)]
            resto = [a_ for a_ in asuntos if a_ not in destacados]
            for a_ in _orden_interes(destacados, op):
                estado_ = ABREV_ESTADO.get(a_["estado"], (a_["estado"] or "").lower())
                pon = f" · ponencia {a_['ponente']}" if a_["ponente"] else ""
                L.append(f"- **{a_['tipo']} {a_['numero']}**{pon}{f' · {estado_}' if estado_ else ''} — "
                         f"{_desc(a_, 160)}{_etiquetas(a_.get('materias', []), op)}")
            if resto:
                L += ["", "_De trámite u otras materias:_"] + _agrupado(resto, True)
            L.append("")
            divididas = [v for v in ses["votaciones"] if re.search(r"mayor[ií]a|en contra", v, re.I)
                         and not re.search(r"facultad de atracci[oó]n|reasumir competencia|quede en lista", v, re.I)]
            if divididas:
                L.append("**Votaciones divididas**")
                L += [f"- {v[:600]}{'…' if len(v) > 600 else ''}" for v in divididas]
                otras = len(ses["votaciones"]) - len(divididas)
                if otras:
                    L.append(f"- _…y {otras} votaciones más (unánimes o sobre atracción/reasunción)._")
                L.append("")
            if ses["votos_anunciados"]:
                por_persona: dict[str, Counter] = defaultdict(Counter)
                for v in ses["votos_anunciados"]:
                    quien = "Presidente" if v["quien"].startswith("Presidente") else v["quien"]
                    for tipo_v in _TIPO_VOTO.findall(v["texto"])[:1]:
                        por_persona[quien][tipo_v.lower()] += 1
                plural = {"particular": "particulares"}
                partes = [f"{q}: " + ", ".join(f"{n} {plural.get(t, t + 's') if n > 1 else t}" for t, n in c.items())
                          for q, c in por_persona.items()]
                L += ["**Votos anunciados:** " + " · ".join(partes), ""]
            continue
        grupos: dict = {}
        for a_ in asuntos:
            grupos.setdefault(a_["estado"] or "Sin estado", []).append(a_)
        for estado_ in sorted(grupos, key=lambda e: (e != "Resueltos", e)):
            L.append(f"**{estado_} ({len(grupos[estado_])})**")
            for a_ in grupos[estado_]:
                pon = f" · ponencia {a_['ponente']}" if a_["ponente"] else ""
                L.append(f"- **{a_['tipo']} {a_['numero']}**{pon} — {_desc(a_, 220)}{_etiquetas(a_.get('materias', []), op)}")
            L.append("")
        if ses["votaciones"]:
            L.append("**Votaciones informadas por la Secretaría**")
            L += [f"- {v}" for v in ses["votaciones"]]
            L.append("")
        if ses["votos_anunciados"]:
            L.append("**Votos anunciados**")
            L += [f"- _{v['quien']}:_ {v['texto']}" for v in ses["votos_anunciados"]]
            L.append("")

    for lista in nov.get("agenda", []):
        aviso = " · lista actualizada" if lista.get("actualizada") else ""
        L += [f"## 📅 Agenda: sesión del {lista['fecha']}{aviso}",
              f"{len(lista['asuntos'])} asuntos · [Lista oficial (PDF)]({lista['url']})", ""]
        asuntos = lista["asuntos"]
        if op["formato"] == "compacto":
            destacados = [a_ for a_ in asuntos if not a_.get("tramite") and _visible(a_.get("materias", []), op)]
            resto = [a_ for a_ in asuntos if a_ not in destacados]
        else:
            destacados, resto = asuntos, []
        for a_ in _orden_interes(destacados, op):
            pon = f" · ponencia {a_['ponente']}" if a_["ponente"] else ""
            proy = f" · [proyecto]({a_['proyecto']})" if a_.get("proyecto") else ""
            desde = a_.get("listado_desde", "")
            antes = f" _(en lista desde el {desde})_" if desde and desde.lower() != lista["fecha"].lower() else ""
            if a_.get("historial"):
                antes += " _(" + "; ".join(h[:1].lower() + h[1:] for h in a_["historial"]) + ")_"
            n = 140 if op["formato"] == "compacto" else 160
            L.append(f"- {a_['orden']}. **{a_['tipo']} {a_['numero']}**{pon} — {_desc(a_, n)}{proy}{antes}"
                     f"{_etiquetas(a_.get('materias', []), op)}")
        if resto:
            L += ["", "_De trámite u otras materias:_"] + _agrupado(resto, False)
        L.append("")

    if tesis:
        L += ["## 📚 Tesis y jurisprudencia nuevas (Semanario Judicial)", ""]
        def orden_inst(i):
            n = i.lower()
            return (0 if n == "pleno" or "suprema corte" in n else 1, i)
        for inst in sorted({t["instancia"] or "Sin instancia" for t in tesis}, key=orden_inst):
            grupo = [t for t in tesis if (t["instancia"] or "Sin instancia") == inst]
            nombre = "Pleno de la SCJN" if inst.lower() == "pleno" else inst
            L.append(f"### {nombre} ({len(grupo)})")
            for t in sorted(grupo, key=lambda t: (t["tipo"] != "Jurisprudencia", t["registro"])):
                tipo = "Jurisprudencia" if t["tipo"] == "Jurisprudencia" else "Tesis aislada"
                L.append(f"- **{t['clave'] or 'Sin clave'}** · {tipo} — {t['rubro']}{_etiquetas(t.get('materias_lista', []), op)}  ")
                extra = " · ".join(x for x in (t["materias"], f"publicada {t['fecha_publicacion']}" if t["fecha_publicacion"] else "") if x)
                L.append(f"  {extra} · [registro {t['registro']}]({t['url']})")
                if t.get("precedentes"):
                    pre = t["precedentes"][:320] + ("…" if len(t["precedentes"]) > 320 else "")
                    L.append(f"  _{'Contradicción de criterios' if t.get('contradiccion') else 'Precedente'}:_ {pre}")
                if t.get("referencias"):
                    L.append(f"  _Cita:_ {', '.join(t['referencias'])}")
                votos = t.get("votos_detalle") or [{"descripcion": f"Voto {v}", "url": t["url"]} for v in t.get("votos", [])]
                for v in votos:
                    L.append(f"  _Voto:_ [{v['descripcion']}]({v['url']})")
            L.append("")

    if dof:
        L += ["## 📰 Diario Oficial de la Federación", ""]
        for etiqueta, notas in _orden_dof(dof, prioridad_max):
            L.append(f"### {etiqueta} ({len(notas)})")
            for n in notas:
                kw = f" 🔎 _{', '.join(n['palabras_clave'])}_" if n["palabras_clave"] else ""
                titulo = n["titulo"] or "(SIDOF no dio título)"
                L.append(f"- {n['fecha']} · [{titulo[:300]}]({n['url']}) — {n['organismo'] or n['poder']}{kw}"
                         f"{_etiquetas(n.get('materias', []), op)}")
            L.append("")

    if errores:
        L += ["## ❗ Fuentes con problemas", ""] + [f"- {e}" for e in errores] + [""]
    if not hay_algo(nov, prioridad_max) and not errores:
        L.append("Sin novedades relevantes.")
    if nov.get("instancias"):
        L += ["", "_Tesis nuevas detectadas en el Semanario, por instancia (incluye las que tu configuración no muestra): "
              + "; ".join(nov["instancias"]) + "_"]
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
