"""Semanario Judicial de la Federación (tesis y jurisprudencia).

Usa la API pública (sin documentación oficial) que consume el propio sitio
https://sjf2.scjn.gob.mx. El sitio está detrás de un firewall (Incapsula), así
que primero se visita la página de búsqueda para obtener cookies de sesión.

Estrategia para detectar novedades: recorrer todas las tesis de la época
vigente (Duodécima = código "210") y compararlas contra los números de
registro digital ya vistos, guardados en data/estado.json.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, asdict, field

from .http import nueva_sesion, pausa

SITIO = "https://sjf2.scjn.gob.mx"
API = f"{SITIO}/services/sjftesismicroservice/api/public"
SESION_URL = f"{SITIO}/busqueda-principal-tesis"
ID_APP = "SJFAPP2020"
EPOCAS = {"210": "Duodécima", "200": "Undécima", "100": "Décima"}


class BloqueoFirewall(RuntimeError):
    """El firewall devolvió su página de verificación en vez de JSON."""


@dataclass
class Tesis:
    registro: int
    rubro: str
    clave: str
    tipo: str  # Jurisprudencia | Tesis aislada
    instancia: str
    materias: str
    epoca: str
    fecha_publicacion: str
    texto: str = ""
    precedentes: str = ""
    votos: list[str] = field(default_factory=list)
    notas_publicacion: str = ""
    alertas_vigencia: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{SITIO}/detalle/tesis/{self.registro}"

    def dict(self) -> dict:
        d = asdict(self)
        d["url"] = self.url
        return d


# ----------------------------------------------------------------- utilidades
_TAG = re.compile(r"<[^>]+>")


def limpiar(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, list):
        return ", ".join(x for x in (limpiar(v) for v in valor) if x)
    if isinstance(valor, dict):
        for k in ("nombre", "descripcion", "texto", "asunto", "value"):
            if valor.get(k):
                return limpiar(valor[k])
        return ""
    texto = html.unescape(_TAG.sub(" ", str(valor)))
    return re.sub(r"\s+", " ", texto).strip()


def _tipo(o: dict) -> str:
    t = str(o.get("tipoTesis") or "").lower()
    ta = str(o.get("ta_tj") or "").upper().replace(".", "").replace(" ", "")
    if "jurisprud" in t or ta == "TJ" or str(o.get("tipoDocumento")) == "2":
        return "Jurisprudencia"
    return "Tesis aislada"


def _fecha(valor) -> str:
    """La API entrega la fecha como texto o como epoch en milisegundos."""
    import datetime as dt
    if isinstance(valor, (int, float)) or (isinstance(valor, str) and valor.isdigit() and len(valor) >= 10):
        n = int(valor)
        n = n / 1000 if n > 10**11 else n
        return dt.datetime.fromtimestamp(n, dt.timezone.utc).strftime("%d/%m/%Y")
    return limpiar(valor)


def parsear_tesis(o: dict) -> Tesis:
    registro = o.get("ius") or o.get("registro") or o.get("id") or 0
    votos = []
    for v in o.get("votos") or []:
        votos.append(limpiar(v) if not isinstance(v, dict) else limpiar(
            v.get("tipoVoto") or v.get("titulo") or v.get("rubro") or v))
    return Tesis(
        registro=int(registro),
        rubro=limpiar(o.get("rubro")),
        clave=limpiar(o.get("claveTesis")),
        tipo=_tipo(o),
        instancia=limpiar(o.get("instancia") or o.get("instanciaAbr")),
        materias=limpiar(o.get("materias") or o.get("materia")),
        epoca=limpiar(o.get("epoca") or o.get("epocaAbr")),
        fecha_publicacion=_fecha(o.get("fechaPublicacion") or o.get("fecha")),
        texto=limpiar(o.get("texto")),
        precedentes=limpiar(o.get("precedentes") or o.get("precedente")),
        votos=[v for v in votos if v],
        notas_publicacion=limpiar(o.get("textoPublicacion") or o.get("nota")),
    )


# ------------------------------------------------- detección de cambios de vigencia
# Reglas sin IA: frases con que el Semanario y las propias tesis anuncian que
# un criterio anterior se interrumpe, se sustituye, se supera o queda sin efecto.
PATRONES_VIGENCIA = [
    (re.compile(r"interrump\w*", re.I), "interrupción de jurisprudencia"),
    (re.compile(r"sustitu\w* (?:de )?(?:la )?jurisprudencia", re.I), "sustitución de jurisprudencia"),
    (re.compile(r"(?:queda|quedó|quedan|deja|dejó|dejan) sin efect\w*", re.I), "criterio que queda sin efectos"),
    (re.compile(r"(?:se )?(?:aparta|apartó|abandona|abandonó|super[oóa]\w*) (?:del|el|de la|la) (?:criterio|jurisprudencia|tesis)", re.I), "abandono / superación de criterio"),
    (re.compile(r"contradicci[oó]n de (?:criterios|tesis)", re.I), "proviene de una contradicción de criterios (revisa qué criterio deja de aplicarse)"),
    (re.compile(r"no es obligatori\w*|dej\w* de ser obligatori\w*", re.I), "criterio que deja de ser obligatorio"),
]
_REF_REGISTRO = re.compile(r"registro digital:?\s*(\d{6,8})", re.I)
_REF_CLAVE = re.compile(
    r"\b((?:P|PR|1a|2a|[IVXLC]+\.\d+o)\.?(?:/J)?\.?\s?[A-Z\.]*\s?\d+/\d{4}(?:\s?\(\d+a\.\))?)"
)


def detectar_cambios_vigencia(t: Tesis) -> list[str]:
    cuerpo = " ".join([t.rubro, t.texto, t.precedentes, t.notas_publicacion])
    alertas = []
    for patron, etiqueta in PATRONES_VIGENCIA:
        if patron.search(cuerpo):
            alertas.append(etiqueta)
    if alertas:
        refs = sorted(set(_REF_REGISTRO.findall(cuerpo)))
        claves = sorted(set(c.strip() for c in _REF_CLAVE.findall(cuerpo)) - {t.clave})
        if refs:
            alertas.append("registros mencionados: " + ", ".join(refs))
        if claves:
            alertas.append("tesis mencionadas: " + ", ".join(claves[:8]))
    return alertas


# --------------------------------------------------------------------- cliente
class ClienteSJF:
    def __init__(self):
        self.s = nueva_sesion()
        self._con_sesion = False

    def _sesion(self, forzar: bool = False):
        if self._con_sesion and not forzar:
            return
        self.s.cookies.clear()
        self.s.get(SESION_URL, timeout=30, headers={"Accept": "text/html"})
        self._con_sesion = True
        pausa(6)  # el firewall suele rechazar peticiones en los primeros segundos

    def _json(self, metodo: str, url: str, **kw):
        self._sesion()
        cab = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": SITIO,
            "Referer": f"{SITIO}/listado-resultado-tesis",
            "X-Requested-With": "XMLHttpRequest",
        }
        for intento in range(3):
            r = self.s.request(metodo, url, headers=cab, timeout=45, **kw)
            if r.status_code == 403 or "json" not in r.headers.get("Content-Type", ""):
                self._sesion(forzar=True)
                pausa(5 * (intento + 1))
                continue
            r.raise_for_status()
            return r.json()
        raise BloqueoFirewall(f"El firewall del Semanario bloqueó la petición a {url}")

    @staticmethod
    def cuerpo_busqueda(epocas: list[str]) -> dict:
        def clasif(nombre, valores):
            return {"name": nombre, "value": valores, "allSelected": False,
                    "visible": False, "isMatrix": False}
        return {
            "classifiers": [clasif("idEpoca", epocas), clasif("tipoDocumento", ["1", "2"])],
            "searchTerms": [],
            "bFacet": True,
            "ius": [],
            "idApp": ID_APP,
            "lbSearch": ["Todo"],
            "filterExpression": "",
        }

    def listar(self, epocas: list[str], tam: int = 100, max_paginas: int = 120) -> list[Tesis]:
        cuerpo = self.cuerpo_busqueda(epocas)
        tesis: list[Tesis] = []
        pagina = 0
        while pagina < max_paginas:
            data = self._json("POST", f"{API}/tesis?page={pagina}&size={tam}", json=cuerpo)
            docs = data.get("documents") or []
            tesis.extend(parsear_tesis(d) for d in docs)
            total_pag = data.get("totalPage") or data.get("totalPages") or 1
            pagina += 1
            if not docs or pagina >= total_pag:
                break
            pausa(1.5)
        return tesis

    def detalle(self, registro: int) -> Tesis | None:
        for params in ({"isSemanal": "true"}, {}, {"isGaceta": "true"}):
            try:
                data = self._json("GET", f"{API}/tesis/{registro}", params=params)
            except BloqueoFirewall:
                raise
            except Exception:  # noqa: BLE001 — probamos la siguiente variante
                continue
            if isinstance(data, list):
                data = data[0] if data else {}
            if data and (data.get("rubro") or data.get("texto")):
                return parsear_tesis(data)
        return None


def instancia_permitida(t: Tesis, instancias: list[str]) -> bool:
    if not instancias or "todas" in [i.lower() for i in instancias]:
        return True
    actual = t.instancia.strip().lower()
    return any(actual == i.strip().lower() for i in instancias)
