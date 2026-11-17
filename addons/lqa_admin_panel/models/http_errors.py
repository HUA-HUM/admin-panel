"""Mensajes de error HTTP para el usuario del panel.

Antes, cualquier falla de una API interna llegaba al toast tal cual:
"La API respondio HTTP 400. Detalle: {"message":[...],"statusCode":400}" o el
repr de requests ("HTTPSConnectionPool(host=..., port=443): Read timed out").
Aca se arma una frase en castellano que dice que servicio fallo y que hacer, y
el detalle tecnico queda en el log del servidor, que es donde sirve.

Modulo plano a proposito: se usa desde hilos (conteos del publicador) donde no
hay env de Odoo.
"""

import json
import logging
from urllib.parse import urlparse

import requests

_logger = logging.getLogger(__name__)

# Fragmento del host -> como lo nombra el equipo.
SERVICE_NAMES = (
    ("api.madre", "Madre"),
    ("api.products", "Products API"),
    ("catalog", "Catalog Sync API"),
    ("invoice", "el servicio de facturación"),
    ("cpe", "la Central de Promociones"),
    ("vtex", "VTEX"),
    ("fravega", "Fravega"),
    ("office.com", "Microsoft Teams"),
    ("webhook", "Microsoft Teams"),
)

MAX_API_MESSAGE = 240


def service_name(url):
    host = (urlparse(str(url or "")).hostname or "").lower()
    for fragment, name in SERVICE_NAMES:
        if fragment in host:
            return name
    return "la API interna"


def _capitalize(text):
    return text[:1].upper() + text[1:] if text else text


def extract_api_message(payload):
    """El mensaje util de un cuerpo de error, sin el envoltorio.

    NestJS (madre, products-api) responde {"message": str | [str], "error",
    "statusCode"}; FastAPI responde {"detail": str | [{"msg": ...}]}.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "replace")
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return ""
        try:
            payload = json.loads(text)
        except ValueError:
            # HTML de un proxy (502 de Caddy/nginx) no le dice nada al usuario.
            return "" if text.startswith("<") else text[:MAX_API_MESSAGE]
    if not isinstance(payload, dict):
        return ""
    for key in ("message", "detail", "error_description", "error"):
        value = payload.get(key)
        if isinstance(value, list):
            parts = [
                item.get("msg") if isinstance(item, dict) else str(item)
                for item in value
            ]
            value = "; ".join(part for part in parts if part)
        if isinstance(value, str) and value.strip():
            # "Bad Request" / "Internal Server Error" repiten el codigo.
            if key == "error" and value.strip().lower() in {
                "bad request",
                "unauthorized",
                "forbidden",
                "not found",
                "internal server error",
            }:
                continue
            value = value.strip()
            if len(value) > MAX_API_MESSAGE:
                value = value[: MAX_API_MESSAGE - 1].rstrip() + "…"
            return value
    return ""


def describe_http_error(status_code, payload, url):
    service = service_name(url)
    detail = extract_api_message(payload)
    suffix = f": {detail}" if detail else "."
    if status_code in (400, 422):
        return f"{_capitalize(service)} rechazó los datos enviados{suffix}"
    if status_code == 401:
        return (
            f"{_capitalize(service)} rechazó la credencial del panel. "
            "Revisá la API key en Ajustes."
        )
    if status_code == 403:
        return f"El panel no tiene permiso para esta operación en {service}."
    if status_code == 404:
        return f"{_capitalize(service)} no encontró lo que se pidió{suffix}"
    if status_code == 409:
        return f"{_capitalize(service)} informó un conflicto{suffix}"
    if status_code == 413:
        return f"La solicitud es demasiado grande para {service}."
    if status_code == 429:
        return (
            f"{_capitalize(service)} está recibiendo demasiadas solicitudes. "
            "Probá de nuevo en un minuto."
        )
    if status_code >= 500:
        # El codigo queda: es lo que se le pasa a quien mantiene el servicio.
        return (
            f"{_capitalize(service)} tuvo un error interno (HTTP {status_code}). "
            "Probá de nuevo en unos minutos."
        )
    return f"{_capitalize(service)} respondió con un error (HTTP {status_code}){suffix}"


def describe_request_exception(error, url, timeout=None):
    service = service_name(url)
    if isinstance(error, requests.Timeout):
        wait = f" ({int(timeout)} s)" if timeout else ""
        return (
            f"{_capitalize(service)} no respondió a tiempo{wait}. "
            "Probá de nuevo en unos minutos."
        )
    if isinstance(error, (requests.ConnectionError, requests.exceptions.SSLError)):
        return f"No se pudo conectar con {service}. Probá de nuevo en unos minutos."
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return describe_http_error(
            error.response.status_code, _response_body(error.response), url
        )
    if isinstance(error, ValueError):
        return f"{_capitalize(service)} respondió algo que el panel no pudo leer."
    return f"Falló la comunicación con {service}."


def _response_body(response):
    try:
        return response.json()
    except ValueError:
        return response.text or ""


def log_http_failure(method, url, error=None, response=None):
    """El detalle tecnico va al log, nunca al usuario."""
    clean_url = str(url or "").split("?", 1)[0]
    if response is not None:
        _logger.warning(
            "%s %s -> HTTP %s: %s",
            str(method or "").upper(),
            clean_url,
            response.status_code,
            (response.text or "")[:1500],
        )
    else:
        _logger.warning(
            "%s %s -> %s: %s",
            str(method or "").upper(),
            clean_url,
            type(error).__name__,
            error,
        )
