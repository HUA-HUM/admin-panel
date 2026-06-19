import json
import os

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaGoogleMerchantActionRun(models.Model):
    _name = "lqa.google.merchant.action.run"
    _description = "Ejecucion de acciones de Google Merchant"
    _order = "triggered_at desc, id desc"

    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    action_type = fields.Selection(
        [
            ("publish_all", "Carga masiva de productos"),
            ("delete_all", "Eliminar catalogo completo"),
            ("delete_selected", "Eliminar productos seleccionados"),
        ],
        string="Accion",
        required=True,
        default="delete_all",
        readonly=True,
    )
    status = fields.Selection(
        [
            ("processing", "Procesando"),
            ("completed", "Completado"),
            ("partial", "Parcial"),
            ("failed", "Fallido"),
        ],
        string="Estado",
        required=True,
        default="processing",
        readonly=True,
        index=True,
    )
    message = fields.Text(string="Mensaje", readonly=True)
    response_json = fields.Text(string="Respuesta API", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)
    triggered_at = fields.Datetime(
        string="Ejecutado",
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    finished_at = fields.Datetime(string="Finalizado", readonly=True)

    def to_panel_dict(self):
        self.ensure_one()
        try:
            response = json.loads(self.response_json or "{}")
        except (TypeError, ValueError):
            response = {}
        return {
            "id": self.id,
            "action_type": self.action_type,
            "status": self.status,
            "message": self.message or "",
            "error_message": self.error_message or "",
            "response": response,
            "response_json": (
                json.dumps(response, ensure_ascii=False, indent=2, default=str)
                if response
                else ""
            ),
            "triggered_at": fields.Datetime.to_string(self.triggered_at),
            "finished_at": fields.Datetime.to_string(self.finished_at),
            "user_name": self.user_id.name or "",
        }


class LqaGoogleMerchantActionsService(models.AbstractModel):
    _name = "lqa.google.merchant.actions.service"
    _description = "Servicio de acciones de Google Merchant"

    DEFAULT_PRODUCTS_API_URL = "https://api.products.loquieroaca.com"
    PUBLISH_ALL_PATH = "/api/internal/google-merchant/products/publish-all"
    DELETE_ALL_PATH = "/api/internal/google-merchant/products/delete-all"
    CONFIRMATION_TEXT = "ELIMINAR TODO"
    DEFAULT_TIMEOUT_SECONDS = 180
    DEFAULT_TRIGGER_TIMEOUT_SECONDS = 8

    @api.model
    def publish_all_products(self, options=None):
        self._check_access()
        options = options if isinstance(options, dict) else {}
        payload = {
            "limit": min(max(self._as_int(options.get("limit"), 5), 1), 1000),
            "offset": max(self._as_int(options.get("offset"), 0), 0),
            "maxPages": min(max(self._as_int(options.get("maxPages"), 1), 1), 1000),
        }
        run = self.env["lqa.google.merchant.action.run"].sudo().create(
            {
                "user_id": self.env.user.id,
                "action_type": "publish_all",
                "status": "processing",
                "message": _("Disparando carga masiva en Products API."),
                "response_json": json.dumps(
                    {"request": payload},
                    ensure_ascii=False,
                    default=str,
                ),
            }
        )
        try:
            response = self._trigger_products_job(self.PUBLISH_ALL_PATH, payload)
            response_payload = response if isinstance(response, (dict, list)) else {}
            failed = bool(
                isinstance(response_payload, dict)
                and (
                    response_payload.get("success") is False
                    or self._clean(
                        response_payload.get("status") or response_payload.get("state")
                    ).upper()
                    in {"ERROR", "FAILED", "FAILURE"}
                )
            )
            run.write(
                {
                    "status": "failed" if failed else "processing",
                    "message": ""
                    if failed
                    else _(
                        "Carga masiva enviada. Products API continua procesando en segundo plano."
                    ),
                    "error_message": self._response_message(response_payload)
                    if failed
                    else "",
                    "response_json": json.dumps(
                        {
                            "request": payload,
                            "response": response_payload,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                    "finished_at": fields.Datetime.now() if failed else False,
                }
            )
        except requests.ReadTimeout:
            run.write(
                {
                    "status": "processing",
                    "message": _(
                        "Carga masiva enviada. Products API no respondio enseguida, queda procesando en segundo plano."
                    ),
                    "response_json": json.dumps(
                        {
                            "request": payload,
                            "note": "Read timeout after trigger; treated as background processing.",
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )
        except UserError as error:
            run.write(
                {
                    "status": "failed",
                    "error_message": str(error),
                    "finished_at": fields.Datetime.now(),
                }
            )
        return run.to_panel_dict()

    @api.model
    def delete_all_products(self, confirmation):
        self._check_access()
        if self._clean(confirmation).upper() != self.CONFIRMATION_TEXT:
            raise UserError(
                _("Escribi %s para confirmar la eliminacion total.")
                % self.CONFIRMATION_TEXT
            )

        run = self.env["lqa.google.merchant.action.run"].sudo().create(
            {
                "user_id": self.env.user.id,
                "action_type": "delete_all",
                "status": "processing",
            }
        )
        try:
            response = self.env["lqa.api.client"].request_absolute_json(
                "POST",
                self._join_url(self._products_base_url(), self.DELETE_ALL_PATH),
                timeout=self._timeout(),
            )
            payload = response if isinstance(response, (dict, list)) else {}
            message = self._clean(
                (
                    payload.get("message")
                    or payload.get("detail")
                    or payload.get("description")
                )
                if isinstance(payload, dict)
                else ""
            ) or "La eliminacion total fue enviada correctamente."
            response_status = (
                self._clean(payload.get("status") or payload.get("state")).upper()
                if isinstance(payload, dict)
                else ""
            )
            failed = bool(
                isinstance(payload, dict)
                and (
                    payload.get("success") is False
                    or response_status in {"ERROR", "FAILED", "FAILURE"}
                )
            )
            run.write(
                {
                    "status": "failed" if failed else "completed",
                    "message": "" if failed else message,
                    "error_message": message if failed else "",
                    "response_json": json.dumps(
                        payload,
                        ensure_ascii=False,
                        default=str,
                    ),
                    "finished_at": fields.Datetime.now(),
                }
            )
        except UserError as error:
            run.write(
                {
                    "status": "failed",
                    "error_message": str(error),
                    "finished_at": fields.Datetime.now(),
                }
            )
        return run.to_panel_dict()

    @api.model
    def delete_selected_products(self, products):
        self._check_access()
        raise UserError(
            _(
                "Products API no expone eliminacion individual de Google Merchant. "
                "Usa la eliminacion total del catalogo."
            )
        )

    @api.model
    def get_history(self, limit=30):
        self._check_access()
        limit = min(max(self._as_int(limit, 30), 1), 100)
        runs = self.env["lqa.google.merchant.action.run"].sudo().search(
            [],
            order="triggered_at desc, id desc",
            limit=limit,
        )
        return [run.to_panel_dict() for run in runs]

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(
                _("No tenes permisos para ejecutar acciones de Google Merchant.")
            )

    def _products_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param(
                "lqa_admin_panel.retailers_products_api_url",
                "",
            )
            or os.environ.get("NEXT_PUBLIC_PRODUCTS_API_URL")
            or self.DEFAULT_PRODUCTS_API_URL
        ).strip()

    def _trigger_products_job(self, path, payload):
        url = self._join_url(self._products_base_url(), path)
        try:
            response = requests.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(5, self._trigger_timeout()),
            )
            response.raise_for_status()
        except requests.ReadTimeout:
            raise
        except requests.RequestException as error:
            raise UserError(_("No se pudo conectar con Products API: %s") % error) from error

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw_response": response.text}

    def _timeout(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.retailers_timeout_seconds",
                self.DEFAULT_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(value, self.DEFAULT_TIMEOUT_SECONDS), 30), 300)

    def _trigger_timeout(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.google_merchant_trigger_timeout_seconds",
                self.DEFAULT_TRIGGER_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(value, self.DEFAULT_TRIGGER_TIMEOUT_SECONDS), 1), 30)

    def _response_message(self, payload):
        if not isinstance(payload, dict):
            return ""
        return self._clean(
            payload.get("message")
            or payload.get("detail")
            or payload.get("description")
            or payload.get("error")
        )

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    @staticmethod
    def _as_int(value, default):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _join_url(base, path):
        return "/".join([str(base or "").rstrip("/"), str(path or "").lstrip("/")])
