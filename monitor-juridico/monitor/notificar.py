"""Envío del boletín por correo (SMTP) y/o Telegram.

Se configura con variables de entorno (en GitHub: Settings → Secrets):
  CORREO_REMITENTE, CORREO_CONTRASENA, CORREO_DESTINO
  [opcional] SMTP_HOST (por defecto smtp.gmail.com), SMTP_PUERTO (465)
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
Si no hay variables para un canal, ese canal simplemente se omite.
"""
from __future__ import annotations

import os
import re
import smtplib
from email.message import EmailMessage

import requests


def correo(asunto: str, md: str, html_cuerpo: str) -> bool:
    remitente = os.getenv("CORREO_REMITENTE")
    contrasena = os.getenv("CORREO_CONTRASENA")
    destino = os.getenv("CORREO_DESTINO") or remitente
    if not (remitente and contrasena):
        return False
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = remitente
    msg["To"] = destino
    msg.set_content(md)
    msg.add_alternative(html_cuerpo, subtype="html")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    puerto = int(os.getenv("SMTP_PUERTO", "465"))
    with smtplib.SMTP_SSL(host, puerto, timeout=60) as smtp:
        smtp.login(remitente, contrasena)
        smtp.send_message(msg)
    return True


def _md_a_telegram(md: str) -> str:
    """Telegram (modo HTML) admite <b>, <i> y <a>."""
    import html as h
    t = h.escape(md, quote=False)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"^#{1,3} (.+)$", r"<b>\1</b>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])_(.+?)_(?!\w)", r"<i>\1</i>", t)
    return t


def telegram(md: str) -> bool:
    token = os.getenv("TELEGRAM_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    texto = _md_a_telegram(md)
    # Telegram limita cada mensaje a 4096 caracteres: se parte por líneas
    trozos, actual = [], ""
    for linea in texto.splitlines(keepends=True):
        if len(actual) + len(linea) > 3800:
            trozos.append(actual)
            actual = ""
        actual += linea
    if actual.strip():
        trozos.append(actual)
    for trozo in trozos:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": trozo, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=30,
        )
        r.raise_for_status()
    return True
