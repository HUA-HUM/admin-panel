import json
import os

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
        [("delete_all", "Eliminar catalogo completo")],
        string="Accion",
        required=True,
        default="delete_all",
        readonly=True,
    )
    status = fields.Selection(
        [
            ("processing", "Procesando"),
            ("completed", "Completado"),
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
    DELETE_ALL_PATH = "/api/internal/google-merchant/products/delete-all"
    CONFIRMATION_TEXT = "ELIMINAR TODO"
    DEFAULT_TIMEOUT_SECONDS = 180

    @api.model
    def delete_all_products(self, confirmation):
        self._check_admin_access()
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
                payload={},
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
    def get_history(self, limit=30):
        self._check_admin_access()
        limit = min(max(self._as_int(limit, 30), 1), 100)
        runs = self.env["lqa.google.merchant.action.run"].sudo().search(
            [],
            order="triggered_at desc, id desc",
            limit=limit,
        )
        return [run.to_panel_dict() for run in runs]

    def _check_admin_access(self):
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_admin"):
            raise AccessError(
                _("Solo administradores del panel pueden eliminar el catalogo.")
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
