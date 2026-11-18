"""Cliente HTTP compartido: reintentos, User-Agent de navegador y pausas corteses."""
from __future__ import annotations

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def nueva_sesion() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2,  # 2s, 4s, 8s, 16s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": UA, "Accept-Language": "es-MX,es;q=0.9"})
    return s


def pausa(segundos: float = 1.0) -> None:
    """Espera entre peticiones para no saturar los servidores públicos."""
    time.sleep(segundos)
