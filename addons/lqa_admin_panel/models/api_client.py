import json
import os

import requests

from odoo import _, api, models
from odoo.exceptions import UserError


class LqaApiClient(models.AbstractModel):
    _name = "lqa.api.client"
    _description = "Cliente de APIs internas LQA"

    @api.model
    def _get_config(self):
        params = self.env["ir.config_parameter"].sudo()
        return {
            "environment": params.get_param(
                "lqa_admin_panel.api_environment", "development"
            ),
            "base_url": (
                params.get_param("lqa_admin_panel.api_base_url")
                or os.environ.get("LQA_API_BASE_URL", "")
            ).strip(),
            "token": (
                params.get_param("lqa_admin_panel.api_token")
                or os.environ.get("LQA_API_TOKEN", "")
            ),
            "timeout": int(params.get_param("lqa_admin_panel.api_timeout_seconds", 20)),
            "mercadolibre_path": params.get_param(
                "lqa_admin_panel.mercadolibre_api_path", "/mercadolibre"
            ),
            "automeli_path": params.get_param(
                "lqa_admin_panel.automeli_api_path", "/automeli"
            ),
        }

    @api.model
    def get_module_path(self, module_code, suffix=""):
        config = self._get_config()
        base_path = config.get(f"{module_code}_path")
        if not base_path:
            raise UserError(_("No hay una ruta de API configurada para %s.") % module_code)
        return self._join_url(base_path, suffix)

    @api.model
    def request_json(self, method, path, payload=None, params=None):
        config = self._get_config()
        if not config["base_url"]:
            raise UserError(_("Configura la URL base de API antes de sincronizar."))

        url = self._join_url(config["base_url"], path)
        return self._request_json_url(
            method=method,
            url=url,
            payload=payload,
            params=params,
            token=config["token"],
            timeout=config["timeout"],
        )

    @api.model
    def request_absolute_json(
        self, method, url, payload=None, params=None, headers=None, timeout=None
    ):
        config = self._get_config()
        return self._request_json_url(
            method=method,
            url=url,
            payload=payload,
            params=params,
            token=False,
            timeout=timeout or config["timeout"],
            extra_headers=headers,
        )

    def _request_json_url(
        self,
        method,
        url,
        payload=None,
        params=None,
        token=False,
        timeout=20,
        extra_headers=None,
    ):
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if extra_headers:
            headers.update(extra_headers)

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                data=json.dumps(payload) if payload is not None else None,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise UserError(_("No se pudo conectar con la API interna: %s") % error) from error

        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError as error:
            raise UserError(_("La API respondio con JSON invalido.")) from error

    @staticmethod
    def _join_url(*parts):
        clean_parts = [str(part).strip("/") for part in parts if str(part or "").strip("/")]
        if not clean_parts:
            return ""
        first = clean_parts[0]
        if first.startswith("http://") or first.startswith("https://"):
            return "/".join([first.rstrip("/"), *clean_parts[1:]])
        return "/" + "/".join(clean_parts)
