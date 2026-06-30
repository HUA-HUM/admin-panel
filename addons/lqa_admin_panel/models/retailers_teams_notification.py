import json
import os
from datetime import timedelta
from urllib.parse import quote

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

    DEFAULT_MARKETPLACE_API_URL = "https://api.marketplace.loquieroaca.com"

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
        overview = self._with_fravega_vtex_orders(overview, config)
        candidates = self._new_order_candidates(overview, config)
        if not candidates:
            return {"sent": False, "reason": "no_new_orders"}
        candidates = self._enrich_orders_for_teams(candidates, config)

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
            "marketplace_api_url": self._marketplace_base_url(),
        }

    def _marketplace_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param(
                "lqa_admin_panel.retailers_marketplace_api_url",
                "",
            )
            or params.get_param(
                "lqa_admin_panel.google_merchant_marketplace_api_url",
                "",
            )
            or os.environ.get("NEXT_PUBLIC_MARKETPLACE_API_URL")
            or os.environ.get("MARKETPLACE_API_URL")
            or self.DEFAULT_MARKETPLACE_API_URL
        ).strip()

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

    def _with_fravega_vtex_orders(self, overview, config):
        overview = overview if isinstance(overview, dict) else {}
        try:
            fravega_orders = self._get_fravega_orders(
                config["marketplace_api_url"],
                config["timeout"],
            )
        except UserError:
            return overview
        if not fravega_orders:
            return overview
        current_items = overview.get("items") if isinstance(overview.get("items"), list) else []
        non_fravega_items = [
            item
            for item in current_items
            if str((item or {}).get("marketplace") or "").lower() != "fravega"
        ]
        normalized_fravega = [
            self._normalize_fravega_order_summary(item)
            for item in fravega_orders
            if isinstance(item, dict)
        ]
        items = normalized_fravega + non_fravega_items
        return {
            **overview,
            "items": items,
            "total": len(items),
            "marketplaces": self._marketplace_counts(items),
        }

    def _get_fravega_orders(self, base_url, timeout):
        url = self._join_url(base_url, "/fravega/vtex/orders")
        try:
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise UserError(_("No se pudo consultar ordenes de Fravega: %s") % error) from error
        if not response.content:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("list", "items", "orders", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _normalize_fravega_order_summary(self, item):
        order_id = self._clean_text(item.get("orderId") or item.get("id"))
        marketplace_order_id = self._clean_text(
            item.get("marketplaceOrderId")
            or item.get("marketPlaceOrderId")
            or item.get("marketplace_order_id")
        )
        return {
            "key": order_id or marketplace_order_id,
            "id": order_id,
            "external_id": marketplace_order_id,
            "sequence": self._clean_text(item.get("sequence")),
            "marketplace": "fravega",
            "status": self._clean_text(
                item.get("statusDescription") or item.get("status")
            ),
            "raw_status": self._clean_text(item.get("status")),
            "created_at": self._clean_text(item.get("creationDate")),
            "updated_at": self._clean_text(item.get("lastChange")),
            "buyer": self._clean_text(item.get("clientName")),
            "sku": "",
            "title": "Orden de Fravega",
            "quantity": self._as_int(item.get("totalItems"), 0),
            "total": self._vtex_amount(item.get("totalValue")),
            "currency": self._clean_text(item.get("currencyCode")) or "ARS",
        }

    def _marketplace_counts(self, items):
        counts = {}
        for item in items:
            marketplace = str((item or {}).get("marketplace") or "sin-marketplace").lower()
            counts[marketplace] = counts.get(marketplace, 0) + 1
        return [
            {"marketplace": marketplace, "total": total}
            for marketplace, total in counts.items()
        ]

    def _enrich_orders_for_teams(self, orders, config):
        enriched = []
        for order in orders:
            if str(order.get("marketplace") or "").lower() == "fravega":
                enriched.append(self._enrich_fravega_order(order, config))
            else:
                enriched.append(order)
        return enriched

    def _enrich_fravega_order(self, order, config):
        order_id = self._fravega_order_id(order)
        if not order_id:
            return order
        try:
            detail = self._get_fravega_order_detail(
                order_id,
                config["marketplace_api_url"],
                config["timeout"],
        )
        except UserError:
            return order
        if not isinstance(detail, dict) or not detail.get("orderId"):
            return order
        normalized = self._normalize_fravega_order_detail(detail, order)
        normalized["_teams_order_key"] = order["_teams_order_key"]
        normalized["_teams_detail_source"] = "fravega_vtex"
        return normalized

    def _get_fravega_order_detail(self, order_id, base_url, timeout):
        url = self._join_url(
            base_url,
            f"/fravega/vtex/orders/{quote(order_id, safe='')}",
        )
        try:
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise UserError(_("No se pudo consultar el detalle de Fravega: %s") % error) from error
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}

    def _normalize_fravega_order_detail(self, detail, fallback):
        detail = detail if isinstance(detail, dict) else {}
        items = detail.get("items") if isinstance(detail.get("items"), list) else []
        first_item = items[0] if items and isinstance(items[0], dict) else {}
        client = detail.get("clientProfileData")
        client = client if isinstance(client, dict) else {}
        shipping = detail.get("shippingData")
        shipping = shipping if isinstance(shipping, dict) else {}
        address = shipping.get("address")
        address = address if isinstance(address, dict) else {}
        logistics = shipping.get("logisticsInfo")
        logistics = logistics if isinstance(logistics, list) else []
        first_logistic = logistics[0] if logistics and isinstance(logistics[0], dict) else {}
        totals = detail.get("totals") if isinstance(detail.get("totals"), list) else []
        shipping_total = self._vtex_total(totals, "Shipping")
        items_total = self._vtex_total(totals, "Items")
        total = (
            self._vtex_amount(detail.get("value"))
            if detail.get("value") is not None
            else self._as_float(fallback.get("total"), 0)
        )
        first_name = self._clean_text(client.get("firstName"))
        last_name = self._clean_text(client.get("lastName"))
        buyer = self._clean_text(" ".join(part for part in (first_name, last_name) if part))
        return {
            **fallback,
            "id": detail.get("orderId") or fallback.get("id") or "",
            "external_id": (
                detail.get("marketplaceOrderId")
                or fallback.get("external_id")
                or ""
            ),
            "sequence": detail.get("sequence") or "",
            "marketplace": "fravega",
            "status": detail.get("statusDescription") or detail.get("status") or fallback.get("status") or "",
            "raw_status": detail.get("status") or fallback.get("raw_status") or "",
            "created_at": detail.get("creationDate") or fallback.get("created_at") or "",
            "updated_at": detail.get("lastChange") or fallback.get("updated_at") or "",
            "buyer": buyer or fallback.get("buyer") or "",
            "buyer_email": self._clean_text(client.get("email")),
            "buyer_document": self._clean_text(client.get("document")),
            "buyer_phone": self._clean_text(client.get("phone")),
            "sku": first_item.get("refId") or fallback.get("sku") or "",
            "seller_sku": first_item.get("sellerSku") or "",
            "title": first_item.get("name") or fallback.get("title") or "",
            "quantity": self._as_int(first_item.get("quantity"), fallback.get("quantity") or 0),
            "unit_price": (
                self._vtex_amount(first_item.get("sellingPrice") or first_item.get("price"))
                if (first_item.get("sellingPrice") or first_item.get("price")) is not None
                else 0
            ),
            "total": total,
            "items_total": self._vtex_amount(items_total) if items_total is not None else total,
            "shipping_total": self._vtex_amount(shipping_total),
            "currency": self._clean_text(
                self._nested_get(detail, ("storePreferencesData", "currencyCode"))
            )
            or fallback.get("currency")
            or "ARS",
            "image_url": first_item.get("imageUrl") or "",
            "product_url": self._fravega_product_url(first_item.get("detailUrl")),
            "shipping_city": self._clean_text(address.get("city")),
            "shipping_state": self._clean_text(address.get("state")),
            "shipping_postal_code": self._clean_text(address.get("postalCode")),
            "shipping_street": self._address_line(address),
            "shipping_method": self._clean_text(first_logistic.get("selectedSla")),
            "shipping_courier": self._clean_text(first_logistic.get("deliveryCompany")),
            "shipping_estimate": self._clean_text(first_logistic.get("shippingEstimate")),
            "raw_detail": detail,
        }

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
        base = [
            f"**{marketplace}** - `{order_id}`",
            f"{title}",
            f"SKU: `{sku}` | Estado: `{status}` | Total: **{total}** | Fecha: {created_at}",
        ]
        if str(order.get("marketplace") or "").lower() == "fravega":
            base.extend(self._fravega_markdown_lines(order))
        return "  \n".join(line for line in base if line)

    def _fravega_markdown_lines(self, order):
        lines = []
        if order.get("buyer"):
            lines.append(f"Cliente: **{order['buyer']}**")
        if order.get("quantity") or order.get("seller_sku") or order.get("sequence"):
            lines.append(
                " | ".join(
                    part
                    for part in [
                        f"Cantidad: {order.get('quantity')}" if order.get("quantity") else "",
                        f"Seller SKU: `{order.get('seller_sku')}`" if order.get("seller_sku") else "",
                        f"Secuencia: `{order.get('sequence')}`" if order.get("sequence") else "",
                    ]
                    if part
                )
            )
        shipping = " - ".join(
            part
            for part in [
                order.get("shipping_city") or "",
                order.get("shipping_state") or "",
                order.get("shipping_postal_code") or "",
            ]
            if part
        )
        if shipping:
            lines.append(f"Destino: {shipping}")
        if order.get("shipping_method") or order.get("shipping_courier") or order.get("shipping_estimate"):
            lines.append(
                "Envio: "
                + " | ".join(
                    part
                    for part in [
                        order.get("shipping_method") or "",
                        order.get("shipping_courier") or "",
                        f"ETA {order.get('shipping_estimate')}" if order.get("shipping_estimate") else "",
                    ]
                    if part
                )
            )
        if order.get("product_url"):
            lines.append(f"[Ver producto]({order['product_url']})")
        return lines

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

    def _fravega_order_id(self, order):
        for key in ("id", "order_id", "external_id"):
            value = self._clean_text(order.get(key))
            if value.startswith("FVG-"):
                return value
        value = self._clean_text(order.get("id") or order.get("external_id"))
        return value

    def _fravega_product_url(self, detail_url):
        detail_url = self._clean_text(detail_url)
        if not detail_url:
            return ""
        if detail_url.startswith(("http://", "https://")):
            return detail_url
        return f"https://www.fravega.com{detail_url if detail_url.startswith('/') else '/' + detail_url}"

    def _address_line(self, address):
        return " ".join(
            part
            for part in [
                self._clean_text(address.get("street")),
                self._clean_text(address.get("number")),
            ]
            if part
        )

    def _vtex_total(self, totals, total_id):
        for total in totals:
            if isinstance(total, dict) and total.get("id") == total_id:
                return total.get("value")
        return None

    def _vtex_amount(self, value):
        if value in (None, ""):
            return 0
        return self._as_float(value, 0) / 100

    @staticmethod
    def _join_url(base_url, path):
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _nested_get(data, path):
        current = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _clean_text(value):
        return str(value or "").strip()

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
