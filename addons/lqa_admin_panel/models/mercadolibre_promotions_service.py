from math import ceil
import json
import threading

import requests

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.modules.registry import Registry


class LqaMercadolibrePromotionActionLog(models.Model):
    _name = "lqa.mercadolibre.promotion.action.log"
    _description = "Log de acciones Central de Promociones"
    _order = "create_date desc, id desc"

    action_key = fields.Char(string="Accion", required=True, readonly=True)
    action_label = fields.Char(string="Etiqueta", required=True, readonly=True)
    promotion_id = fields.Char(string="Promotion ID", readonly=True)
    updated_by = fields.Char(string="Updated by", readonly=True)
    requested_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Solicitado por",
        readonly=True,
    )
    status = fields.Selection(
        selection=[
            ("queued", "En cola"),
            ("running", "Ejecutando"),
            ("completed", "Completado"),
            ("failed", "Fallido"),
        ],
        default="queued",
        required=True,
        readonly=True,
    )
    started_at = fields.Datetime(string="Inicio", readonly=True)
    finished_at = fields.Datetime(string="Fin", readonly=True)
    request_payload = fields.Text(string="Payload", readonly=True)
    response_payload = fields.Text(string="Respuesta", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)


class LqaMercadolibrePromotionsService(models.AbstractModel):
    _name = "lqa.mercadolibre.promotions.service"
    _description = "Servicio de Central de Promociones MercadoLibre"

    DEFAULT_STATS_ENDPOINT = "http://cpe.loquieroaca.com/promotions/stats"
    DEFAULT_PROMOTIONS_ENDPOINT = "http://cpe.loquieroaca.com/promotions"
    DEFAULT_CATALOGS_ENDPOINT = "http://cpe.loquieroaca.com/promotions/catalogs"
    DEFAULT_ORDERS_ENDPOINT = (
        "https://api.madre.loquieroaca.com/"
        "api/mercadolibre/orders/aporte-ml"
    )
    DEFAULT_ANALYTICS_ENDPOINT = (
        "https://api.madre.loquieroaca.com/"
        "api/mercadolibre/orders/analytics/aporte-ml/timeseries"
    )
    DEFAULT_TIMEOUT_SECONDS = 120
    DEFAULT_ACTION_TIMEOUT_SECONDS = 300
    DEFAULT_DATADOG_SERVICE = "central-promos-enginee"
    DEFAULT_DATADOG_BASE_URL = "https://us5.datadoghq.com/logs/livetail"
    ACTIONS = {
        "sync": {
            "label": "Sincronizar campanas",
            "description": "Actualiza estado y datos de promociones desde MELI hacia la central.",
            "endpoint_param": "lqa_admin_panel.mercadolibre_promotions_sync_url",
            "default_endpoint": "http://cpe.loquieroaca.com/promotions/sync",
            "danger": "medium",
        },
        "activate": {
            "label": "Scheduler de activacion",
            "description": "Evalua promociones aptas y activa las que cumplen reglas economicas.",
            "endpoint_param": "lqa_admin_panel.mercadolibre_promotions_activate_url",
            "default_endpoint": "http://cpe.loquieroaca.com/promotions/activate",
            "danger": "high",
        },
        "deactivate": {
            "label": "Scheduler de desactivacion",
            "description": "Revisa promociones activas y desparticipa las que ya no cumplen criterios.",
            "endpoint_param": "lqa_admin_panel.mercadolibre_promotions_deactivate_url",
            "default_endpoint": "http://cpe.loquieroaca.com/promotions/deactivate",
            "danger": "high",
        },
        "deactivate_failed": {
            "label": "Reintentar desactivaciones fallidas",
            "description": "Reintenta promociones que quedaron en estado FAILED_DEACTIVATION.",
            "endpoint_param": "lqa_admin_panel.mercadolibre_promotions_deactivate_failed_url",
            "default_endpoint": "http://cpe.loquieroaca.com/promotions/deactivate-failed",
            "danger": "high",
        },
        "sync_one": {
            "label": "Sincronizar una campana puntual",
            "description": "Actualiza una promocion especifica por promotionId.",
            "endpoint_param": "lqa_admin_panel.mercadolibre_promotions_sync_one_url",
            "default_endpoint": "http://cpe.loquieroaca.com/promotions/sync-one",
            "danger": "medium",
            "requires_promotion_id": True,
        },
    }
    PROMOTION_TYPES = [
        ("smart", "SMART"),
        ("deal", "DEAL"),
        ("preNegotiated", "PRE_NEGOTIATED"),
    ]
    STATUS_LABELS = {
        "active": "Activas",
        "synced": "Synced",
        "finished": "Finalizadas",
        "deleted": "Eliminadas",
        "pending": "Pendientes",
        "paused": "Pausadas",
        "failedSync": "Failed sync",
        "failedActivation": "Fallidas act.",
        "failedDeactivation": "Fallidas desact.",
    }
    STATUS_ORDER = [
        "active",
        "synced",
        "finished",
        "deleted",
        "pending",
        "paused",
        "failedSync",
        "failedActivation",
        "failedDeactivation",
    ]

    @api.model
    def get_stats(self):
        self._check_access()
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._endpoint(
                "lqa_admin_panel.mercadolibre_promotions_stats_url",
                self.DEFAULT_STATS_ENDPOINT,
            ),
            timeout=self._timeout(),
        )
        return self._normalize_stats(response or {})

    @api.model
    def get_promotions(self, filters=None):
        self._check_access()
        params = self._pagination_params(filters or {}, default_limit=100)
        status = self._clean(filters or {}, "status")
        promo_type = self._clean(filters or {}, "type")
        if status:
            params["status"] = status.upper()
        if promo_type:
            params["type"] = promo_type.upper()

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._endpoint(
                "lqa_admin_panel.mercadolibre_promotions_url",
                self.DEFAULT_PROMOTIONS_ENDPOINT,
            ),
            params=params,
            timeout=self._timeout(),
        )
        items = response.get("items") or response.get("promotions") or []
        return {
            "items": [self._normalize_promotion(item) for item in items],
            "pagination": self._normalize_pagination(response, params),
        }

    @api.model
    def get_catalogs(self, filters=None):
        self._check_access()
        params = self._pagination_params(filters or {}, default_limit=100)
        promo_type = self._clean(filters or {}, "type")
        if promo_type:
            params["type"] = promo_type.upper()

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._endpoint(
                "lqa_admin_panel.mercadolibre_promotions_catalogs_url",
                self.DEFAULT_CATALOGS_ENDPOINT,
            ),
            params=params,
            timeout=self._timeout(),
        )
        items = response.get("items") or response.get("catalogs") or []
        normalized = [self._normalize_catalog(item) for item in items]
        return {
            "items": normalized,
            "summary": self._catalog_summary(normalized, response),
            "pagination": self._normalize_pagination(response, params),
        }

    @api.model
    def get_orders(self, filters=None):
        self._check_access()
        params = self._offset_params(filters or {}, default_limit=50, max_limit=100)
        status = self._clean(filters or {}, "status") or "paid"
        if status != "all":
            params["status"] = status

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._endpoint(
                "lqa_admin_panel.mercadolibre_aporte_orders_url",
                self.DEFAULT_ORDERS_ENDPOINT,
            ),
            params=params,
            timeout=self._timeout(),
        )
        items = response.get("items") or response.get("orders") or []
        normalized = [self._normalize_order(item) for item in items]
        return {
            "items": normalized,
            "summary": self._orders_summary(normalized, response),
            "pagination": self._normalize_offset_pagination(response, params),
        }

    @api.model
    def get_orders_analytics(self, filters=None):
        self._check_access()
        filters = filters or {}
        from_date = self._date_param(filters.get("fromDate"), start=True)
        to_date = self._date_param(filters.get("toDate"), start=False)
        params = {
            "fromDate": from_date,
            "toDate": to_date,
            "groupBy": self._clean(filters, "groupBy") or "day",
        }
        status = self._clean(filters, "status") or "paid"
        if status != "all":
            params["status"] = status

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._endpoint(
                "lqa_admin_panel.mercadolibre_aporte_analytics_url",
                self.DEFAULT_ANALYTICS_ENDPOINT,
            ),
            params=params,
            timeout=self._timeout(),
        )
        items = response.get("items") if isinstance(response, dict) else response
        series = [self._normalize_series_point(item) for item in (items or [])]
        return {
            "series": series,
            "summary": self._analytics_summary(series),
        }

    @api.model
    def get_actions_context(self):
        self._check_access()
        params = self.env["ir.config_parameter"].sudo()
        can_execute = self.env.user.has_group("lqa_admin_panel.group_lqa_admin")
        return {
            "can_execute": can_execute,
            "updated_by": self.env.user.login or self.env.user.name,
            "actions": [
                {
                    "key": key,
                    "label": config["label"],
                    "description": config["description"],
                    "danger": config["danger"],
                    "requires_promotion_id": bool(config.get("requires_promotion_id")),
                }
                for key, config in self.ACTIONS.items()
            ],
            "history": self._action_history(),
            "datadog": {
                "base_url": params.get_param(
                    "lqa_admin_panel.mercadolibre_promotions_datadog_base_url",
                    self.DEFAULT_DATADOG_BASE_URL,
                ),
                "service": params.get_param(
                    "lqa_admin_panel.mercadolibre_promotions_datadog_service",
                    self.DEFAULT_DATADOG_SERVICE,
                ),
            },
        }

    @api.model
    def run_action(self, action_key, values=None):
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_admin"):
            raise AccessError(_("Solo administradores del panel pueden ejecutar acciones."))

        action_key = self._clean({"value": action_key}, "value")
        config = self.ACTIONS.get(action_key)
        if not config:
            raise UserError(_("Accion no valida."))

        values = values or {}
        updated_by = self._clean(values, "updatedBy") or self.env.user.login or self.env.user.name
        promotion_id = self._clean(values, "promotionId")
        if config.get("requires_promotion_id") and not promotion_id:
            raise UserError(_("Ingresa el promotionId que queres sincronizar."))

        payload = {"updatedBy": updated_by}
        if promotion_id:
            payload["promotionId"] = promotion_id

        endpoint = self._endpoint(config["endpoint_param"], config["default_endpoint"])
        log = (
            self.env["lqa.mercadolibre.promotion.action.log"]
            .sudo()
            .create(
                {
                    "action_key": action_key,
                    "action_label": config["label"],
                    "promotion_id": promotion_id,
                    "updated_by": updated_by,
                    "requested_by_id": self.env.user.id,
                    "status": "queued",
                    "request_payload": json.dumps(payload, ensure_ascii=False),
                }
            )
        )
        thread = threading.Thread(
            target=self._execute_action_thread,
            args=(self.env.cr.dbname, log.id, endpoint, payload, self._action_timeout()),
            daemon=True,
        )
        thread.start()
        return self._serialize_action_log(log)

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(_("No tenes permisos para consultar promociones."))

    def _endpoint(self, parameter, default):
        endpoint = (
            self.env["ir.config_parameter"].sudo().get_param(parameter, default)
            or default
        )
        if not endpoint:
            raise UserError(_("Configura el endpoint de la Central de Promociones."))
        return endpoint

    def _timeout(self):
        timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.mercadolibre_promotions_timeout_seconds",
                self.DEFAULT_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(timeout, self.DEFAULT_TIMEOUT_SECONDS), 30), 300)

    def _action_timeout(self):
        timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.mercadolibre_promotions_action_timeout_seconds",
                self.DEFAULT_ACTION_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(timeout, self.DEFAULT_ACTION_TIMEOUT_SECONDS), 60), 900)

    def _action_history(self, limit=30):
        logs = (
            self.env["lqa.mercadolibre.promotion.action.log"]
            .sudo()
            .search([], limit=limit)
        )
        return [self._serialize_action_log(log) for log in logs]

    def _serialize_action_log(self, log):
        return {
            "id": log.id,
            "action_key": log.action_key,
            "action_label": log.action_label,
            "promotion_id": log.promotion_id or "",
            "updated_by": log.updated_by or "",
            "requested_by": log.requested_by_id.name or "",
            "status": log.status,
            "started_at": fields.Datetime.to_string(log.started_at) if log.started_at else "",
            "finished_at": fields.Datetime.to_string(log.finished_at) if log.finished_at else "",
            "created_at": fields.Datetime.to_string(log.create_date) if log.create_date else "",
            "response_payload": log.response_payload or "",
            "error_message": log.error_message or "",
        }

    @staticmethod
    def _execute_action_thread(dbname, log_id, endpoint, payload, timeout):
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            log = env["lqa.mercadolibre.promotion.action.log"].browse(log_id)
            if not log.exists():
                return
            log.write({"status": "running", "started_at": fields.Datetime.now()})
            cr.commit()
            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers={"Accept": "application/json"},
                    timeout=timeout,
                )
                response.raise_for_status()
                try:
                    response_payload = response.json()
                except ValueError:
                    response_payload = {"text": response.text}
                log.write(
                    {
                        "status": "completed",
                        "finished_at": fields.Datetime.now(),
                        "response_payload": json.dumps(
                            response_payload,
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )
            except requests.RequestException as error:
                log.write(
                    {
                        "status": "failed",
                        "finished_at": fields.Datetime.now(),
                        "error_message": str(error),
                    }
                )
            except Exception as error:
                log.write(
                    {
                        "status": "failed",
                        "finished_at": fields.Datetime.now(),
                        "error_message": str(error),
                    }
                )
            cr.commit()

    def _pagination_params(self, filters, default_limit=100, max_limit=100):
        page = max(self._as_int(filters.get("page"), 1), 1)
        limit = min(max(self._as_int(filters.get("limit"), default_limit), 1), max_limit)
        return {
            "page": page,
            "limit": limit,
        }

    def _offset_params(self, filters, default_limit=50, max_limit=100):
        limit = min(max(self._as_int(filters.get("limit"), default_limit), 1), max_limit)
        offset = max(self._as_int(filters.get("offset"), 0), 0)
        return {
            "offset": offset,
            "limit": limit,
        }

    def _normalize_pagination(self, response, params):
        total = self._as_int(response.get("total"), 0)
        page = self._as_int(response.get("page"), params.get("page", 1))
        limit = self._as_int(response.get("limit"), params.get("limit", 100))
        total_pages = self._as_int(
            response.get("totalPages"),
            ceil(total / limit) if limit else 1,
        )
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
        }

    def _normalize_offset_pagination(self, response, params):
        total = self._as_int(response.get("total"), 0)
        limit = self._as_int(response.get("limit"), params.get("limit", 50))
        offset = self._as_int(response.get("offset"), params.get("offset", 0))
        count = self._as_int(response.get("count"), len(response.get("items") or []))
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "count": count,
            "page": (offset // limit) + 1 if limit else 1,
            "total_pages": ceil(total / limit) if limit else 1,
            "has_next": bool(response.get("hasNext")),
            "has_previous": offset > 0,
            "next_offset": response.get("nextOffset"),
        }

    def _normalize_stats(self, stats):
        cards = []
        total = self._as_int(stats.get("total"), 0)
        for key, label in self.PROMOTION_TYPES:
            raw = stats.get(key) or {}
            cards.append(
                {
                    "key": key,
                    "label": label,
                    "total": self._as_int(raw.get("total"), 0),
                    "statuses": [
                        {
                            "key": status,
                            "label": self.STATUS_LABELS[status],
                            "value": self._as_int(raw.get(status), 0),
                        }
                        for status in self.STATUS_ORDER
                    ],
                }
            )
        return {
            "total": total or sum(card["total"] for card in cards),
            "cards": cards,
        }

    def _normalize_promotion(self, promotion):
        prices = promotion.get("prices") or {}
        economics = promotion.get("economics") or {}
        metadata = promotion.get("metadata") or {}
        audit_trail = promotion.get("auditTrail") or []
        last_audit = audit_trail[-1] if audit_trail else {}
        return {
            "id": promotion.get("_id") or promotion.get("id") or "",
            "promotion_id": promotion.get("promotionId") or "",
            "item_id": promotion.get("itemId") or "",
            "name": promotion.get("name") or "Sin nombre",
            "type": promotion.get("type") or "",
            "status": promotion.get("status") or "",
            "sku": promotion.get("sku") or "",
            "category_id": promotion.get("categoryId") or "",
            "listing_type": promotion.get("listingTypeId") or "",
            "start_date": promotion.get("startDate"),
            "finish_date": promotion.get("finishDate"),
            "deadline_date": promotion.get("deadlineDate"),
            "original_price": self._as_float(prices.get("originalPrice"), None),
            "suggested_price": self._as_float(prices.get("suggestedPrice"), None),
            "cost": self._as_float(economics.get("cost"), None),
            "profit": self._as_float(economics.get("profit"), None),
            "profitability": self._as_float(economics.get("profitability"), None),
            "margin": self._as_float(economics.get("margin"), None),
            "profitable": bool(economics.get("profitable")),
            "should_pause": bool(economics.get("shouldPause")),
            "source_process": metadata.get("sourceProcess") or "",
            "status_reason": metadata.get("statusReason") or "",
            "updated_at": promotion.get("updatedAt") or metadata.get("syncedAt"),
            "last_audit": {
                "process": last_audit.get("process") or "",
                "status": last_audit.get("status") or "",
                "reason": last_audit.get("reason") or "",
                "executed_at": last_audit.get("executedAt"),
            },
        }

    def _normalize_catalog(self, catalog):
        return {
            "id": catalog.get("_id") or catalog.get("id") or "",
            "promotion_id": catalog.get("promotionId") or "",
            "name": catalog.get("name") or "Sin nombre",
            "type": catalog.get("type") or "",
            "status": catalog.get("status") or "",
            "total_candidates": self._as_int(catalog.get("totalCandidates"), 0),
            "start_date": catalog.get("startDate"),
            "finish_date": catalog.get("finishDate"),
            "deadline_date": catalog.get("deadlineDate"),
            "updated_at": catalog.get("updatedAt"),
        }

    def _catalog_summary(self, items, response):
        by_type = {}
        for item in items:
            key = item["type"] or "SIN_TIPO"
            bucket = by_type.setdefault(
                key,
                {"type": key, "promotions": 0, "candidates": 0, "names": []},
            )
            bucket["promotions"] += 1
            bucket["candidates"] += item["total_candidates"]
            if len(bucket["names"]) < 3:
                bucket["names"].append(item["name"])
        return {
            "visible": len(items),
            "total": self._as_int(response.get("total"), len(items)),
            "types": list(by_type.values()),
        }

    def _normalize_order(self, order):
        return {
            "id": order.get("id") or order.get("_id") or "",
            "sale_number": order.get("nroVenta") or "",
            "payment_id": order.get("paymentId") or "",
            "sku": order.get("sku") or "",
            "status": order.get("estadoOrden") or "",
            "sale_date": order.get("fechaVenta"),
            "product_name": order.get("nombreProducto") or "Sin producto",
            "units": self._as_int(order.get("cantidadUnidades"), 0),
            "sale_price": self._as_float(order.get("precioVenta"), 0),
            "aporte_ml": self._as_float(order.get("aporteMl"), 0),
            "revenue": self._as_float(order.get("saldoMercadolibre"), 0),
            "commission": self._as_float(order.get("comisionMl"), 0),
            "city": order.get("ciudad") or "",
            "province": order.get("provincia") or "",
            "link_ml": order.get("linkMl") or "",
            "link_amazon": order.get("linkAmazon") or "",
        }

    def _orders_summary(self, items, response):
        total_orders = self._as_int(response.get("total"), len(items))
        aporte = sum(item["aporte_ml"] for item in items)
        revenue = sum(item["revenue"] for item in items)
        return {
            "orders": total_orders,
            "visible_orders": len(items),
            "aporte_ml": aporte,
            "revenue": revenue,
            "average_aporte": aporte / len(items) if items else 0,
        }

    def _normalize_series_point(self, point):
        return {
            "date": point.get("date") or "",
            "aporte_ml": self._as_float(point.get("aporteMl"), 0),
            "orders": self._as_int(point.get("orders"), 0),
            "revenue": self._as_float(point.get("revenue"), 0),
        }

    def _analytics_summary(self, series):
        aporte = sum(point["aporte_ml"] for point in series)
        orders = sum(point["orders"] for point in series)
        revenue = sum(point["revenue"] for point in series)
        peak = max(series, key=lambda point: point["aporte_ml"], default={})
        return {
            "aporte_ml": aporte,
            "orders": orders,
            "revenue": revenue,
            "average_aporte": aporte / orders if orders else 0,
            "peak_date": peak.get("date") or "",
            "peak_aporte": peak.get("aporte_ml") or 0,
        }

    def _date_param(self, value, start=True):
        if value:
            normalized = str(value).strip().replace("T", " ")
            if len(normalized) == 10:
                normalized += " 00:00:00" if start else " 23:59:59"
            return normalized
        today = fields.Date.context_today(self)
        first_day = today.replace(day=1)
        if start:
            return f"{first_day.isoformat()} 00:00:00"
        return f"{today.isoformat()} 23:59:59"

    @staticmethod
    def _clean(filters, key):
        return str(filters.get(key) or "").strip()

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
