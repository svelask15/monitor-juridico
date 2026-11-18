"""Agenda del Pleno: listas oficiales de asuntos para las próximas sesiones.

Listado: https://www.scjn.gob.mx/pleno/secretaria-general-de-acuerdos/listas-para-sesion
Cada PDF trae, por asunto: número en la lista, expediente, desde cuándo está
listado, descripción, ponencia y una liga "VER PROYECTO" al proyecto de sentencia.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, asdict, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .http import nueva_sesion, pausa
from .sesiones import NUMERO, _plano, _titulo, texto_pdf

SITIO = "https://www.scjn.gob.mx"
LISTADO = SITIO + "/pleno/secretaria-general-de-acuerdos/listas-para-sesion?page={pagina}"
MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}

_ASUNTO = re.compile(
    r"(?<!\d)(\d{1,3})\. (" + NUMERO + r") (?:VER )?(?:PROYECTO )?"
    r"(?:\(Listado por primera vez el ([^)]+)\) )?"
    r"(.+?)\(PONENCIA (?:DE LA|DEL|DE) (?:SEÑORA? )?(?:MINISTR[OA] )?(?:PRESIDENT[EA] )?([^)]+)\)\.?",
    re.I,
)
_TIPO = re.compile(r"^((?:[A-ZÁÉÍÓÚÑ]+ ?)+?)(?= [a-záéíóúñ]| *[.,(]|$)")
_FECHA_SESION = re.compile(r"DEL (?:LUNES|MARTES|MIÉRCOLES|JUEVES|VIERNES) (\d{1,2} DE \w+ DE \d{4})", re.I)


@dataclass
class Lista:
    url: str
    fecha: str  # "19 de noviembre de 2026"
    asuntos: list[dict] = field(default_factory=list)
    actualizada: bool = False  # ya se había enviado una versión anterior de esta lista

    def dict(self) -> dict:
        return asdict(self)


def fecha_iso(texto: str) -> str | None:
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", texto or "", re.I)
    if not m or m.group(2).lower() not in MESES:
        return None
    return f"{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


def parsear_listado(html_texto: str) -> list[dict]:
    sopa = BeautifulSoup(html_texto, "html.parser")
    filas = []
    for tr in sopa.find_all("tr"):
        a = tr.find("a", href=re.compile(r"\.pdf", re.I))
        if not a:
            continue
        celdas = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        fecha = celdas[0] if celdas else a.get_text(" ", strip=True)
        filas.append({"fecha": fecha, "iso": fecha_iso(fecha) or fecha_iso(a["href"].replace("%20", " ")),
                      "url": urljoin(SITIO, a["href"])})
    return filas


def ligas_proyectos(contenido: bytes) -> list[str]:
    from pypdf import PdfReader
    urls = []
    for p in PdfReader(io.BytesIO(contenido)).pages:
        for ref in p.get("/Annots") or []:
            a = ref.get_object().get("/A") or {}
            uri = a.get("/URI") if hasattr(a, "get") else None
            if uri and uri not in urls:
                urls.append(str(uri))
    return urls


def _liga_para(numero: str, urls: list[str]) -> str:
    """'360/2026' ↔ '.../CC360_2026.pdf'; '1/2026-CA' ↔ '..._AI1_2026_CA.pdf'."""
    m = re.match(r"(\d+)/(\d{4})(?:-([A-Z]+))?", numero)
    if not m:
        return ""
    n, anio, sufijo = m.groups()
    fin = rf"[_-]?{sufijo}\.pdf$" if sufijo else r"\.pdf$"
    patron = re.compile(rf"(?<!\d){n}_{anio}{fin}", re.I)
    return next((u for u in urls if patron.search(u.rsplit("/", 1)[-1])), "")


def parsear_lista(texto: str, url: str, fecha: str = "", urls_proyectos: list[str] | None = None) -> Lista:
    plano = _plano(texto)
    corte = re.search(r"EL SECRETARIO GENERAL|LA SECRETARIA GENERAL", plano)
    if corte:
        plano = plano[:corte.start()]  # lo demás es la firma electrónica
    f = _FECHA_SESION.search(plano)
    asuntos = []
    for m in _ASUNTO.finditer(plano):
        orden, numero, primera, desc, ponente = m.groups()
        desc = re.sub(r"\s+", " ", desc).strip(" .")
        t = _TIPO.match(desc)
        tipo = t.group(1).strip() if t else ""
        asuntos.append({
            "orden": int(orden),
            "numero": numero,
            "tipo": _titulo(tipo),
            "descripcion": desc[len(tipo):].strip(" ,.") if tipo else desc,
            "ponente": _titulo(" ".join(ponente.split()[-2:])) if ponente else "",
            "ponente_completo": _titulo(ponente.strip()),
            "listado_desde": (primera or "").strip(),
            "proyecto": _liga_para(numero, urls_proyectos or []),
        })
    return Lista(url=url, fecha=(f.group(1).lower() if f else fecha), asuntos=asuntos)


def obtener(hoy_iso: str, vistas: dict[str, str]) -> list[Lista]:
    """Listas de sesiones de hoy en adelante que no se han enviado (o que cambiaron).

    `vistas` = {fecha_iso: url} de lo ya enviado; se actualiza aquí mismo.
    """
    s = nueva_sesion()
    r = s.get(LISTADO.format(pagina=0), timeout=30)
    r.raise_for_status()
    nuevas = []
    for fila in parsear_listado(r.text):
        if not fila["iso"] or fila["iso"] < hoy_iso or vistas.get(fila["iso"]) == fila["url"]:
            continue
        pausa(1)
        pdf = s.get(fila["url"], timeout=90)
        pdf.raise_for_status()
        lista = parsear_lista(texto_pdf(pdf.content), fila["url"], fila["fecha"], ligas_proyectos(pdf.content))
        lista.actualizada = fila["iso"] in vistas
        vistas[fila["iso"]] = fila["url"]
        nuevas.append(lista)
    return sorted(nuevas, key=lambda x: fecha_iso(x.fecha) or "")
