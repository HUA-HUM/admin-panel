import json
import os
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LqaRetailersTeamsNotification(models.Model):
    _name = "lqa.retailers.teams.notification"
    _description = "Notificacion Teams de orden Retailer"
    _order = "notified_at desc, id desc"

    order_key = fields.Char(required=True, readonly=True, index=True)
    marketplace = fields.Char(readonly=True, index=True)
    order_id = fields.Char(readonly=True, index=True)
    status = fields.Char(readonly=True)
    sku = fields.Char(readonly=True)
    title = fields.Char(readonly=True)
    total = fields.Float(readonly=True)
    currency = fields.Char(readonly=True)
    order_created_at = fields.Char(readonly=True)
    notified_at = fields.Datetime(
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    payload_json = fields.Text(readonly=True)

    _sql_constraints = [
        (
            "order_key_unique",
            "unique(order_key)",
            "Esta orden ya fue notificada a Teams.",
        ),
    ]

    @api.model
    def _cron_notify_new_orders(self):
        config = self._teams_config()
        if not config["enabled"] or not config["webhook_url"]:
            return {"sent": False, "reason": "disabled"}

        overview = (
            self.env["lqa.retailers.service"]
            .sudo()
            .get_orders_overview(config["mode"], {})
        )
        candidates = self._new_order_candidates(overview, config)
        if not candidates:
            return {"sent": False, "reason": "no_new_orders"}

        payload = self._build_teams_payload(candidates, overview, config)
        self._post_to_teams(config["webhook_url"], payload, config["timeout"])
        self._store_notified_orders(candidates)
        self._cleanup_old_notifications(config["retention_days"])
        return {"sent": True, "count": len(candidates)}

    @api.model
    def send_test_notification(self):
        config = self._teams_config()
        if not config["webhook_url"]:
            raise UserError(_("Configura primero el webhook de Microsoft Teams."))
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "Prueba Panel Comercial",
            "themeColor": "FF4F5A",
            "title": "Prueba de notificaciones Retailers",
            "text": (
                "El Panel Comercial ya puede enviar notificaciones a Microsoft Teams."
            ),
        }
        self._post_to_teams(config["webhook_url"], payload, config["timeout"])
        return {"sent": True}

    def _teams_config(self):
        params = self.env["ir.config_parameter"].sudo()
        mode = (
            params.get_param("lqa_admin_panel.retailers_teams_orders_mode", "")
            or os.environ.get("LQA_TEAMS_ORDERS_MODE")
            or "last24"
        ).strip()
        if mode not in {"last24", "recent24", "recent48", "recent72"}:
            mode = "last24"
        return {
            "enabled": self._as_bool(
                params.get_param(
                    "lqa_admin_panel.retailers_teams_notifications_enabled", "0"
                )
            ),
            "webhook_url": (
                params.get_param("lqa_admin_panel.retailers_teams_webhook_url", "")
                or os.environ.get("LQA_TEAMS_WEBHOOK_URL", "")
            ).strip(),
            "mode": mode,
            "statuses": self._csv_values(
                params.get_param("lqa_admin_panel.retailers_teams_order_statuses", "")
                or os.environ.get("LQA_TEAMS_ORDER_STATUSES", "")
            ),
            "max_orders": min(
                max(
                    self._as_int(
                        params.get_param(
                            "lqa_admin_panel.retailers_teams_max_orders_per_message",
                            20,
                        ),
                        20,
                    ),
                    1,
                ),
                50,
            ),
            "timeout": min(
                max(
                    self._as_int(
                        params.get_param(
                            "lqa_admin_panel.retailers_teams_timeout_seconds",
                            20,
                        ),
                        20,
                    ),
                    5,
                ),
                60,
            ),
            "retention_days": min(
                max(
                    self._as_int(
                        params.get_param(
                            "lqa_admin_panel.retailers_teams_retention_days",
                            45,
                        ),
                        45,
                    ),
                    7,
                ),
                365,
            ),
        }

    def _new_order_candidates(self, overview, config):
        items = overview.get("items") if isinstance(overview, dict) else []
        statuses = {status.upper() for status in config["statuses"]}
        candidates = []
        for item in items or []:
            item = item if isinstance(item, dict) else {}
            if statuses and str(item.get("status") or "").upper() not in statuses:
                continue
            key = self._order_key(item)
            if not key or self.search([("order_key", "=", key)], limit=1):
                continue
            candidates.append({**item, "_teams_order_key": key})
            if len(candidates) >= config["max_orders"]:
                break
        return candidates

    def _store_notified_orders(self, orders):
        values = []
        for order in orders:
            values.append(
                {
                    "order_key": order["_teams_order_key"],
                    "marketplace": order.get("marketplace") or "",
                    "order_id": order.get("id") or order.get("external_id") or "",
                    "status": order.get("status") or "",
                    "sku": order.get("sku") or "",
                    "title": order.get("title") or "",
                    "total": self._as_float(order.get("total"), 0),
                    "currency": order.get("currency") or "ARS",
                    "order_created_at": order.get("created_at") or "",
                    "payload_json": json.dumps(order, ensure_ascii=False, default=str),
                }
            )
        if values:
            self.sudo().create(values)

    def _build_teams_payload(self, orders, overview, config):
        total_amount = sum(self._as_float(order.get("total"), 0) for order in orders)
        title = _("Nuevas ordenes de marketplaces")
        summary = _("%s ordenes nuevas") % len(orders)
        facts = [
            {"name": "Ordenes nuevas", "value": str(len(orders))},
            {"name": "Periodo", "value": self._range_label(overview, config["mode"])},
            {"name": "Total aprox.", "value": self._format_currency(total_amount)},
        ]
        sections = [
            {
                "activityTitle": summary,
                "activitySubtitle": "Panel Comercial - Retailers",
                "facts": facts,
                "markdown": True,
            },
            {
                "title": "Detalle",
                "text": "\n\n".join(self._order_markdown(order) for order in orders),
                "markdown": True,
            },
        ]
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": summary,
            "themeColor": "FF4F5A",
            "title": title,
            "sections": sections,
        }

    def _order_markdown(self, order):
        marketplace = self._marketplace_label(order.get("marketplace"))
        order_id = order.get("id") or order.get("external_id") or "Sin ID"
        title = order.get("title") or "Orden de marketplace"
        sku = order.get("sku") or "-"
        status = order.get("status") or "-"
        total = self._format_currency(order.get("total"), order.get("currency") or "ARS")
        created_at = order.get("created_at") or "-"
        return (
            f"**{marketplace}** - `{order_id}`  \n"
            f"{title}  \n"
            f"SKU: `{sku}` | Estado: `{status}` | Total: **{total}** | Fecha: {created_at}"
        )

    def _post_to_teams(self, webhook_url, payload, timeout):
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise UserError(_("No se pudo enviar la notificacion a Teams: %s") % error) from error

    def _cleanup_old_notifications(self, retention_days):
        limit_date = fields.Datetime.now() - timedelta(days=retention_days)
        old_records = self.search([("notified_at", "<", fields.Datetime.to_string(limit_date))])
        old_records.unlink()

    def _order_key(self, order):
        marketplace = str(order.get("marketplace") or "").strip().lower()
        order_id = str(order.get("id") or order.get("external_id") or "").strip()
        if order_id:
            return f"{marketplace}|{order_id}"
        fallback = "|".join(
            str(order.get(key) or "").strip()
            for key in ("sku", "created_at", "total", "status")
        )
        return f"{marketplace}|{fallback}" if fallback.strip("|") else ""

    def _range_label(self, overview, mode):
        range_data = overview.get("range") if isinstance(overview, dict) else {}
        if isinstance(range_data, dict) and (range_data.get("from") or range_data.get("to")):
            return f"{range_data.get('from') or '-'} - {range_data.get('to') or '-'}"
        return {
            "last24": "Ultimas 24h",
            "recent24": "Ultimas 24h",
            "recent48": "Ultimas 48h",
            "recent72": "Ultimas 72h",
        }.get(mode, mode)

    def _marketplace_label(self, value):
        return {
            "fravega": "Fravega",
            "megatone": "Megatone",
            "oncity": "OnCity",
        }.get(str(value or "").lower(), str(value or "Marketplace"))

    def _format_currency(self, value, currency="ARS"):
        amount = self._as_float(value, 0)
        symbol = "$" if currency == "ARS" else currency
        return f"{symbol} {amount:,.0f}".replace(",", ".")

    @staticmethod
    def _csv_values(value):
        return [item.strip() for item in str(value or "").split(",") if item.strip()]

    @staticmethod
    def _as_bool(value):
        return str(value or "").strip().lower() in {"1", "true", "yes", "si", "on"}

    @staticmethod
    def _as_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
