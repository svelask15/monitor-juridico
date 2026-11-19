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
    contradiccion: bool = False  # la jurisprudencia resuelve una contradicción de criterios
    referencias: list[str] = field(default_factory=list)  # tesis/registros que cita
    votos_detalle: list[dict] = field(default_factory=list)

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
    ta = str(o.get("ta_tj") if o.get("ta_tj") is not None else "").upper().replace(".", "").replace(" ", "")
    if "jurisprud" in t or t == "1" or ta in ("TJ", "1") or str(o.get("tipoDocumento")) == "2":
        return "Jurisprudencia"
    clave = str(o.get("claveTesis") or "")
    if "/J." in clave.replace(" ", "") or " J/" in clave:
        return "Jurisprudencia"
    return "Tesis aislada"


_CLAVE_SCJN = re.compile(r"^\s*(P|1a|2a)\.")


def instancia_legible(o: dict) -> str:
    """'S.C.J.N.' + clave 'P./J. 2/2021' → 'Pleno'; '1a. …' → 'Primera Sala'; '2a. …' → 'Segunda Sala'."""
    inst = limpiar(o.get("instancia") or o.get("instanciaAbr"))
    if inst.upper().replace(" ", "") in ("S.C.J.N.", "SCJN") or "suprema corte" in inst.lower():
        clave = str(o.get("claveTesis") or "")
        if clave.strip().startswith("1a."):
            return "Primera Sala"
        if clave.strip().startswith("2a."):
            return "Segunda Sala"
        return "Pleno"
    return {"T.C.C.": "Tribunales Colegiados de Circuito", "P.C.": "Plenos de Circuito",
            "P.R.": "Plenos Regionales"}.get(inst, inst)


def es_scjn(t) -> bool:
    """Acepta un objeto Tesis o un dict."""
    inst = (t.instancia if hasattr(t, "instancia") else t.get("instancia", "")) or ""
    clave = (t.clave if hasattr(t, "clave") else t.get("clave", "")) or ""
    i = inst.strip().lower()
    return (i in ("pleno", "primera sala", "segunda sala", "s.c.j.n.", "scjn") or "suprema corte" in i
            or (bool(_CLAVE_SCJN.match(clave)) and "regional" not in i and "circuito" not in i))


def _fecha(valor) -> str:
    """La API entrega la fecha como texto, ISO ("2026-10-30 10:40:00.0") o epoch en ms."""
    import datetime as dt
    if isinstance(valor, (int, float)) or (isinstance(valor, str) and valor.isdigit() and len(valor) >= 10):
        n = int(valor)
        n = n / 1000 if n > 10**11 else n
        return dt.datetime.fromtimestamp(n, dt.timezone.utc).strftime("%d/%m/%Y")
    texto = limpiar(valor)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", texto)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else texto


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
        instancia=instancia_legible(o),
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
    (re.compile(r"no es obligatori\w*|dej\w* de ser obligatori\w*", re.I), "criterio que deja de ser obligatorio"),
]
_REF_REGISTRO = re.compile(r"registro digital:?\s*(\d{6,8})", re.I)
_REF_CLAVE = re.compile(
    r"\b((?:P|PR|1a|2a|[IVXLC]+\.\d+o)\.?(?:/J)?\.?\s?[A-Z\.]*\s?\d+/\d{4}(?:\s?\(\d+a\.\))?)"
)


_CDC = re.compile(r"contradicci[oó]n de (?:criterios|tesis)", re.I)


def detectar_cambios_vigencia(t: Tesis) -> list[str]:
    """Llena t.contradiccion y t.referencias; devuelve solo las alertas fuertes.

    Que una jurisprudencia venga de una contradicción de criterios es normal
    (casi todas las de Plenos Regionales), así que eso NO es alerta: se marca
    aparte. Alerta = el texto dice expresamente que un criterio se interrumpe,
    se sustituye, se abandona o queda sin efectos.
    """
    cuerpo = " ".join([t.rubro, t.texto, t.precedentes, t.notas_publicacion])
    t.contradiccion = bool(_CDC.search(t.precedentes) or _CDC.search(t.rubro))
    refs = [f"registro {r}" for r in sorted(set(_REF_REGISTRO.findall(cuerpo)))]
    claves = sorted(set(c.strip() for c in _REF_CLAVE.findall(cuerpo)) - {t.clave})
    t.referencias = (claves[:8] + refs)[:10]
    return [etiqueta for patron, etiqueta in PATRONES_VIGENCIA if patron.search(cuerpo)]


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

    def pagina_scjn(self, epoca: str, pagina: int, tam: int = 200) -> tuple[list[dict], int]:
        """Una página de tesis de la SCJN (Pleno y Salas) de una época. Devuelve (documentos crudos, total de páginas)."""
        cuerpo = self.cuerpo_busqueda([epoca])
        cuerpo["classifiers"].append({"name": "instancia", "value": ["Suprema Corte de Justicia de la Nación"],
                                      "allSelected": False, "visible": False, "isMatrix": False})
        data = self._json("POST", f"{API}/tesis?page={pagina}&size={tam}", json=cuerpo)
        return data.get("documents") or [], int(data.get("totalPage") or data.get("totalPages") or 1)

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


VOTOS_API = f"{SITIO}/services/sjfvotosmicroservice/api/public/votos"
_TIPO_VOTO = re.compile(r"\bvotos?\s+(particular|concurrente|aclaratorio|minoritario|de minoría|paralelo|razonado|disidente)", re.I)


def describir_voto(texto: str) -> str:
    """Primera línea del voto, p. ej. 'Voto particular que formula la Magistrada …'."""
    primera = next((l.strip() for l in re.split(r"(?<=\.)\s+|\n", limpiar(texto)) if l.strip()), "")
    return primera[:180]


def _voto(self, id_voto: int) -> dict:
    url = f"{SITIO}/detalle/voto/{id_voto}"
    for params in ({"isSemanal": "true"}, {}):
        try:
            data = self._json("GET", f"{VOTOS_API}/{id_voto}", params=params)
        except BloqueoFirewall:
            break
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, list):
            data = data[0] if data else {}
        texto = (data or {}).get("texto") or (data or {}).get("rubro") or ""
        if texto:
            return {"id": id_voto, "url": url, "descripcion": describir_voto(texto)}
    return {"id": id_voto, "url": url, "descripcion": f"Voto {id_voto}"}


ClienteSJF.voto = _voto


def _norm(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def instancia_permitida(t: Tesis, instancias: list[str]) -> bool:
    """'Pleno' = coincidencia exacta; cualquier otro valor = 'contiene'
    (p. ej. 'Suprema Corte' acepta 'Pleno de la Suprema Corte de Justicia...')."""
    if not instancias or "todas" in [i.lower() for i in instancias]:
        return True
    actual = _norm(t.instancia)
    if es_scjn(t) and any(_norm(i) in ("pleno", "suprema corte", "scjn", "s.c.j.n.") for i in instancias):
        return True
    for i in map(_norm, instancias):
        if actual == i or (i != "pleno" and i in actual):
            return True
    return False
