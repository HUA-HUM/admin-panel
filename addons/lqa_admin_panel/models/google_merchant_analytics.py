import json
import os
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaGoogleMerchantPerformanceQuery(models.Model):
    _name = "lqa.google.merchant.performance.query"
    _description = "Consulta de performance Google Merchant"
    _order = "queried_at desc, id desc"

    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    sku = fields.Char(string="SKU", required=True, readonly=True, index=True)
    date_from = fields.Date(string="Desde", required=True, readonly=True)
    date_to = fields.Date(string="Hasta", required=True, readonly=True)
    status = fields.Selection(
        [
            ("completed", "Completado"),
            ("failed", "Fallido"),
        ],
        string="Estado",
        required=True,
        default="completed",
        readonly=True,
        index=True,
    )
    clicks = fields.Integer(string="Clicks", readonly=True)
    impressions = fields.Integer(string="Impresiones", readonly=True)
    click_through_rate = fields.Float(string="CTR", readonly=True)
    rows_count = fields.Integer(string="Filas", readonly=True)
    rows_json = fields.Text(string="Filas API", readonly=True)
    response_json = fields.Text(string="Respuesta API", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)
    queried_at = fields.Datetime(
        string="Consultado",
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )

    def to_panel_dict(self):
        self.ensure_one()
        rows = self._json_loads(self.rows_json, [])
        response = self._json_loads(self.response_json, {})
        return {
            "id": self.id,
            "sku": self.sku or "",
            "from": fields.Date.to_string(self.date_from) if self.date_from else "",
            "to": fields.Date.to_string(self.date_to) if self.date_to else "",
            "status": self.status or "",
            "clicks": self.clicks,
            "impressions": self.impressions,
            "clickThroughRate": self.click_through_rate,
            "rowsCount": self.rows_count,
            "rows": rows if isinstance(rows, list) else [],
            "response": response,
            "responseJson": (
                json.dumps(response, ensure_ascii=False, indent=2, default=str)
                if response
                else ""
            ),
            "errorMessage": self.error_message or "",
            "queriedAt": fields.Datetime.to_string(self.queried_at),
            "userName": self.user_id.name or "",
        }

    @staticmethod
    def _json_loads(value, default):
        try:
            return json.loads(value or "")
        except (TypeError, ValueError):
            return default


class LqaGoogleMerchantAnalyticsService(models.AbstractModel):
    _name = "lqa.google.merchant.analytics.service"
    _description = "Servicio de analytics Google Merchant"

    DEFAULT_MARKETPLACE_API_URL = "https://api.marketplace.loquieroaca.com"
    PERFORMANCE_PATH = "/internal/google-merchant/products/{sku}/performance"
    DEFAULT_TIMEOUT_SECONDS = 180

    @api.model
    def query_performance(self, filters=None):
        self._check_access()
        filters = filters if isinstance(filters, dict) else {}
        sku = self._clean(filters.get("sku"))
        date_from = self._parse_date(filters.get("from") or filters.get("date_from"))
        date_to = self._parse_date(filters.get("to") or filters.get("date_to"))
        if not sku:
            raise UserError(_("Ingresa un SKU para consultar performance."))
        if not date_from or not date_to:
            raise UserError(_("Completa fecha desde y hasta."))
        if date_from > date_to:
            raise UserError(_("La fecha desde no puede ser mayor a la fecha hasta."))

        record_values = {
            "user_id": self.env.user.id,
            "sku": sku,
            "date_from": date_from,
            "date_to": date_to,
        }
        try:
            response = self._fetch_performance(sku, date_from, date_to)
            payload = response if isinstance(response, dict) else {}
            rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
            record = (
                self.env["lqa.google.merchant.performance.query"]
                .sudo()
                .create(
                    {
                        **record_values,
                        "status": "completed",
                        "clicks": self._as_int(payload.get("clicks"), 0),
                        "impressions": self._as_int(payload.get("impressions"), 0),
                        "click_through_rate": self._as_float(
                            payload.get("clickThroughRate"), 0.0
                        ),
                        "rows_count": len(rows),
                        "rows_json": json.dumps(
                            rows,
                            ensure_ascii=False,
                            default=str,
                        ),
                        "response_json": json.dumps(
                            payload,
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )
            )
            return record.to_panel_dict()
        except UserError as error:
            record = (
                self.env["lqa.google.merchant.performance.query"]
                .sudo()
                .create(
                    {
                        **record_values,
                        "status": "failed",
                        "error_message": str(error),
                        "response_json": json.dumps(
                            {"error": str(error)},
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )
            )
            raise UserError(str(error)) from error

    @api.model
    def get_history(self, limit=50, sku=""):
        self._check_access()
        limit = min(max(self._as_int(limit, 50), 1), 200)
        domain = []
        sku = self._clean(sku)
        if sku:
            domain.append(("sku", "ilike", sku))
        records = (
            self.env["lqa.google.merchant.performance.query"]
            .sudo()
            .search(domain, order="queried_at desc, id desc", limit=limit)
        )
        return [record.to_panel_dict() for record in records]

    def _fetch_performance(self, sku, date_from, date_to):
        path = self.PERFORMANCE_PATH.format(sku=quote(self._clean(sku), safe=""))
        return self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(self._marketplace_base_url(), path),
            params={
                "from": fields.Date.to_string(date_from),
                "to": fields.Date.to_string(date_to),
            },
            timeout=self._timeout(),
        )

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(
                _("No tenes permisos para consultar analytics de Google Merchant.")
            )

    def _marketplace_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param(
                "lqa_admin_panel.google_merchant_marketplace_api_url",
                "",
            )
            or os.environ.get("NEXT_PUBLIC_MARKETPLACE_API_URL")
            or os.environ.get("MARKETPLACE_API_URL")
            or self.DEFAULT_MARKETPLACE_API_URL
        ).strip()

    def _timeout(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.google_merchant_analytics_timeout_seconds",
                self.DEFAULT_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(value, self.DEFAULT_TIMEOUT_SECONDS), 30), 300)

    @staticmethod
    def _parse_date(value):
        value = str(value or "").strip()
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except (TypeError, ValueError) as error:
            raise UserError(_("La fecha %s no es valida.") % value) from error

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    @staticmethod
    def _as_int(value, default=0):
        try:
            return int(float(value or default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value, default=0.0):
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _join_url(*parts):
        clean_parts = [str(part).strip("/") for part in parts if str(part or "").strip("/")]
        if not clean_parts:
            return ""
        first = clean_parts[0]
        if first.startswith("http://") or first.startswith("https://"):
            return "/".join([first.rstrip("/"), *clean_parts[1:]])
        return "/" + "/".join(clean_parts)
