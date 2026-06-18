import json
import os
from urllib.parse import urlsplit, urlunsplit

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaRetailersService(models.AbstractModel):
    _name = "lqa.retailers.service"
    _description = "Servicio de retailers y marketplaces"

    DEFAULT_MADRE_API_URL = "https://api.madre.loquieroaca.com"
    DEFAULT_PRODUCTS_API_URL = "https://api.products.loquieroaca.com"
    DEFAULT_ORDERS_PROXY_URL = "https://order.api.loquieroaca.com/orders"
    DEFAULT_TIMEOUT_SECONDS = 60
    DEFAULT_ORDERS_TIMEOUT_SECONDS = 90
    ORDER_MARKETPLACES = ("fravega", "megatone", "oncity")
    REFRESH_PUBLISHED_MARKETPLACES = ("fravega", "megatone", "oncity")
    MARKETPLACES = {
        "oncity": {
            "name": "OnCity",
            "description": "Publicaciones y sincronizaciones para OnCity.",
            "accent": "oncity",
            "logo": "/lqa_admin_panel/static/src/img/marketplace/oncity.png?v=1",
        },
        "fravega": {
            "name": "Fravega",
            "description": "Catalogo, stock y precios publicados en Fravega.",
            "accent": "fravega",
            "logo": "/lqa_admin_panel/static/src/img/marketplace/fravega.png?v=1",
        },
        "google-merchant": {
            "name": "Google Merchant",
            "description": "Feed y publicaciones para Google Merchant Center.",
            "accent": "google",
            "logo": "/lqa_admin_panel/static/src/img/marketplace/google-merchant.png?v=1",
        },
        "megatone": {
            "name": "Megatone",
            "description": "Productos, importaciones y estados de Megatone.",
            "accent": "megatone",
            "logo": "/lqa_admin_panel/static/src/img/marketplace/megatone.svg?v=1",
        },
    }

    @api.model
    def get_marketplaces(self):
        self._check_access()
        return [
            {"id": marketplace_id, **values}
            for marketplace_id, values in self.MARKETPLACES.items()
        ]

    @api.model
    def get_products(self, marketplace_id, filters=None):
        self._check_access()
        marketplace_id = self._validate_marketplace(marketplace_id)
        filters = filters or {}
        limit = min(max(self._as_int(filters.get("limit"), 10), 1), 100)
        offset = max(self._as_int(filters.get("offset"), 0), 0)
        params = {
            "marketplace": marketplace_id,
            "offset": offset,
            "limit": limit,
        }
        sku = self._clean(filters.get("sku"))
        status = self._clean(filters.get("status"))
        if sku:
            params["sku"] = sku
        if status:
            params["status"] = status

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(self._madre_base_url(), "/api/internal/marketplace/products/items/all"),
            params=params,
            timeout=self._timeout(),
        )
        items = self._response_items(response)
        total = self._as_int(response.get("total"), len(items)) if isinstance(response, dict) else len(items)
        count = self._as_int(response.get("count"), len(items)) if isinstance(response, dict) else len(items)
        has_next = bool(response.get("hasNext")) if isinstance(response, dict) else offset + limit < total
        next_offset = response.get("nextOffset") if isinstance(response, dict) else offset + limit
        return {
            "items": [self._normalize_product(item) for item in items],
            "summary": self._normalize_product_summary(response),
            "pagination": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "count": count,
                "has_previous": offset > 0,
                "has_next": has_next,
                "next_offset": next_offset if next_offset is not None else offset + limit,
                "page": (offset // limit) + 1 if limit else 1,
            },
        }

    @api.model
    def get_import_runs(self, marketplace_id, filters=None):
        self._check_access()
        marketplace_id = self._validate_marketplace(marketplace_id)
        filters = filters or {}
        limit = min(max(self._as_int(filters.get("limit"), 20), 1), 100)
        offset = max(self._as_int(filters.get("offset"), 0), 0)
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(self._madre_base_url(), "/api/internal/product-sync/runs"),
            params={
                "marketplace": marketplace_id,
                "offset": offset,
                "limit": limit,
            },
            timeout=self._timeout(),
        )
        items = self._response_items(response)
        items = sorted(
            [self._normalize_import_run(item) for item in items],
            key=lambda item: item.get("started_at") or "",
            reverse=True,
        )
        total = self._as_int(response.get("total"), len(items)) if isinstance(response, dict) else len(items)
        return {
            "items": items,
            "pagination": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "count": len(items),
                "has_previous": offset > 0,
                "has_next": offset + limit < total,
                "next_offset": offset + limit,
                "page": (offset // limit) + 1 if limit else 1,
            },
        }

    @api.model
    def run_import(self, marketplace_id):
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_admin"):
            raise AccessError(_("Solo administradores del panel pueden disparar imports."))
        marketplace_id = self._validate_marketplace(marketplace_id)
        response = self.env["lqa.api.client"].request_absolute_json(
            "POST",
            self._join_url(
                self._products_base_url(),
                f"/api/internal/import/{marketplace_id}/run",
            ),
            timeout=self._timeout(),
        )
        response = response if isinstance(response, dict) else {}
        return {
            "status": self._clean(response.get("status")) or self._clean(response.get("state")) or "QUEUED",
            "message": self._clean(response.get("message") or response.get("detail")),
            "raw": response,
        }

    @api.model
    def get_status(self, marketplace_id):
        self._check_access()
        marketplace_id = self._validate_marketplace(marketplace_id)
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(
                self._madre_base_url(),
                f"/api/internal/marketplace/products/{marketplace_id}/status",
            ),
            timeout=self._timeout(),
        )
        return self._normalize_status(response or {})

    @api.model
    def get_orders_overview(self, mode="last24", filters=None):
        self._check_access()
        mode = self._clean(mode) or "last24"
        filters = filters or {}
        if mode == "custom":
            return self._get_custom_orders(filters)

        path_by_mode = {
            "last24": "/overview/last-24-hours",
            "recent24": "/overview/recent/24",
            "recent48": "/overview/recent/48",
            "recent72": "/overview/recent/72",
            "historical": "/overview/historical",
        }
        path = path_by_mode.get(mode)
        if not path:
            raise UserError(_("Periodo de ordenes no valido."))

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(self._orders_base_url(), path),
            headers=self._orders_headers(),
            timeout=self._orders_timeout(),
        )
        return self._normalize_orders_response(response, mode)

    @api.model
    def refresh_published(self, marketplace_id):
        self._check_access()
        marketplace_id = self._clean(marketplace_id).lower()
        if marketplace_id not in self.REFRESH_PUBLISHED_MARKETPLACES:
            raise UserError(_("Marketplace no disponible para actualizacion masiva."))

        response = self.env["lqa.api.client"].request_absolute_json(
            "POST",
            self._join_url(
                self._products_base_url(),
                f"/api/internal/marketplace-changes/refresh-published/{marketplace_id}",
            ),
            payload={},
            timeout=self._timeout(),
        )
        payload = response if isinstance(response, dict) else {}
        marketplace = self.MARKETPLACES.get(marketplace_id, {})
        return {
            "marketplace": marketplace_id,
            "marketplace_name": marketplace.get("name") or marketplace_id,
            "status": self._clean(
                payload.get("status")
                or payload.get("state")
                or payload.get("result")
                or "QUEUED"
            ),
            "message": self._clean(
                payload.get("message")
                or payload.get("detail")
                or payload.get("description")
            ),
            "triggered_at": fields.Datetime.to_string(fields.Datetime.now()),
            "raw": payload,
        }

    def _check_access(self):
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_commercial_user"):
            raise AccessError(_("No tenes permisos para consultar retailers."))

    def _validate_marketplace(self, marketplace_id):
        marketplace_id = self._clean(marketplace_id)
        if marketplace_id not in self.MARKETPLACES:
            raise UserError(_("Marketplace no valido."))
        return marketplace_id

    def _madre_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param(
                "lqa_admin_panel.retailers_madre_api_url",
                "",
            )
            or os.environ.get("NEXT_PUBLIC_MADRE_API_URL")
            or self.DEFAULT_MADRE_API_URL
        ).strip()

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

    def _orders_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        configured = (
            params.get_param("lqa_admin_panel.retailers_orders_proxy_url", "")
            or os.environ.get("NEXT_PUBLIC_ORDERS_API_URL", "")
        ).strip()
        if configured:
            return self._normalize_orders_base(configured, proxy=True)

        backend = os.environ.get("ORDERS_API_URL", "").strip()
        if backend:
            return self._normalize_orders_base(backend, proxy=False)

        return self.DEFAULT_ORDERS_PROXY_URL

    def _orders_headers(self):
        params = self.env["ir.config_parameter"].sudo()
        token = (
            params.get_param("lqa_admin_panel.retailers_orders_api_token", "")
            or os.environ.get("ORDERS_API_TOKEN", "")
            or os.environ.get("LQA_ORDERS_API_TOKEN", "")
        ).strip()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _timeout(self):
        timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.retailers_timeout_seconds",
                self.DEFAULT_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(timeout, self.DEFAULT_TIMEOUT_SECONDS), 20), 180)

    def _orders_timeout(self):
        timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.retailers_orders_timeout_seconds",
                self.DEFAULT_ORDERS_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(timeout, self.DEFAULT_ORDERS_TIMEOUT_SECONDS), 30), 240)

    def _get_custom_orders(self, filters):
        marketplace = self._clean(filters.get("marketplace") or "all").lower()
        if marketplace not in ("all", *self.ORDER_MARKETPLACES):
            raise UserError(_("Marketplace de ordenes no valido."))

        date_from = self._clean(filters.get("from") or filters.get("fechaDesde"))
        date_to = self._clean(filters.get("to") or filters.get("fechaHasta"))
        if not date_from or not date_to:
            raise UserError(_("Indica fecha desde y hasta para consultar ordenes."))

        params = {
            "from": date_from,
            "to": date_to,
            "fechaDesde": date_from,
            "fechaHasta": date_to,
        }
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(
                self._orders_base_url(),
                "" if marketplace == "all" else marketplace,
            ),
            params=params,
            headers=self._orders_headers(),
            timeout=self._orders_timeout(),
        )
        normalized = self._normalize_orders_response(response, "custom")
        normalized["selected_marketplace"] = marketplace
        return normalized

    def _normalize_orders_response(self, response, mode):
        payload = response if isinstance(response, dict) else {}
        raw_items = self._response_order_items(response)
        items = [
            self._normalize_order_item(item, index)
            for index, item in enumerate(raw_items)
        ]
        total = self._as_int(
            payload.get("total") or payload.get("count") or payload.get("totalOrders"),
            len(items),
        )
        range_data = payload.get("range") if isinstance(payload.get("range"), dict) else {}
        errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
        return {
            "mode": mode,
            "range": {
                "from": self._clean(range_data.get("from") or payload.get("from")),
                "to": self._clean(range_data.get("to") or payload.get("to")),
            },
            "total": total,
            "marketplaces": self._normalize_order_marketplaces(payload, items),
            "items": items,
            "errors": [
                {"key": f"error-{index}", "message": self._normalize_error(error)}
                for index, error in enumerate(errors)
            ],
        }

    def _normalize_order_item(self, item, index):
        item = item if isinstance(item, dict) else {"value": item}
        lines = self._extract_order_lines(item)
        first_line = lines[0] if lines else {}
        marketplace = self._clean(
            item.get("marketplace")
            or item.get("marketPlace")
            or item.get("channel")
            or item.get("source")
            or first_line.get("marketplace")
        ).lower()
        order_id = self._clean(
            item.get("orderId")
            or item.get("order_id")
            or item.get("id")
            or item.get("_id")
            or item.get("externalId")
            or item.get("external_id")
            or item.get("numeroOrden")
            or item.get("orderNumber")
        )
        total = self._first_number(
            item,
            (
                "total",
                "totalAmount",
                "total_amount",
                "amount",
                "grandTotal",
                "totalPrice",
                "price",
                "revenue",
            ),
        )
        quantity = self._as_int(
            item.get("quantity")
            or item.get("qty")
            or item.get("units")
            or sum(self._as_int(line.get("quantity") or line.get("qty"), 0) for line in lines),
            0,
        )
        sku = self._clean(
            item.get("sku")
            or item.get("sellerSku")
            or item.get("seller_sku")
            or item.get("sellerSKU")
            or first_line.get("sku")
            or first_line.get("sellerSku")
            or first_line.get("seller_sku")
        )
        title = self._clean(
            item.get("title")
            or item.get("productTitle")
            or item.get("product_title")
            or item.get("name")
            or first_line.get("title")
            or first_line.get("name")
            or first_line.get("productTitle")
        )
        return {
            "key": f"{order_id or 'order'}-{index}",
            "id": order_id,
            "marketplace": marketplace,
            "status": self._clean(
                item.get("status") or item.get("state") or item.get("orderStatus")
            ),
            "created_at": self._clean(
                item.get("createdAt")
                or item.get("created_at")
                or item.get("dateCreated")
                or item.get("date_created")
                or item.get("fecha")
                or item.get("fechaCreacion")
            ),
            "updated_at": self._clean(
                item.get("updatedAt") or item.get("updated_at") or item.get("lastUpdated")
            ),
            "buyer": self._normalize_buyer(item.get("buyer") or item.get("customer") or item),
            "sku": sku,
            "title": title or "Orden de marketplace",
            "quantity": quantity,
            "total": total,
            "currency": self._clean(item.get("currency") or item.get("currencyId") or "ARS"),
            "external_id": self._clean(
                item.get("externalId")
                or item.get("external_id")
                or item.get("marketplaceOrderId")
                or item.get("marketplace_order_id")
            ),
            "raw_status": self._clean(item.get("rawStatus") or item.get("raw_status")),
        }

    def _normalize_order_marketplaces(self, payload, items):
        raw_marketplaces = payload.get("marketplaces") if isinstance(payload, dict) else []
        result = []
        if isinstance(raw_marketplaces, dict):
            raw_marketplaces = [
                {"marketplace": marketplace, "total": total}
                for marketplace, total in raw_marketplaces.items()
            ]
        if isinstance(raw_marketplaces, list):
            for item in raw_marketplaces:
                if not isinstance(item, dict):
                    continue
                marketplace = self._clean(
                    item.get("marketplace") or item.get("name") or item.get("id")
                ).lower()
                if marketplace:
                    result.append(
                        {
                            "marketplace": marketplace,
                            "total": self._as_int(item.get("total") or item.get("count"), 0),
                        }
                    )
        if result:
            return result

        counts = {}
        for item in items:
            marketplace = item.get("marketplace") or "sin-marketplace"
            counts[marketplace] = counts.get(marketplace, 0) + 1
        return [
            {"marketplace": marketplace, "total": total}
            for marketplace, total in counts.items()
        ]

    def _normalize_buyer(self, value):
        if isinstance(value, dict):
            return self._clean(
                value.get("name")
                or value.get("fullName")
                or value.get("nickname")
                or value.get("email")
                or value.get("customerName")
                or value.get("buyerName")
                or value.get("id")
            )
        return self._clean(value)

    def _first_number(self, source, keys):
        for key in keys:
            if source.get(key) is not None:
                return self._as_float(source.get(key), None)
        return None

    def _normalize_orders_base(self, value, proxy):
        value = self._clean(value).rstrip("/")
        if not value:
            return self.DEFAULT_ORDERS_PROXY_URL
        parsed = urlsplit(value)
        if parsed.netloc == "order.api.loquieroaca.com":
            path = parsed.path.rstrip("/")
            for suffix in ("/api/orders", "/orders", "/api"):
                if path.endswith(suffix):
                    path = path[: -len(suffix)]
                    break
            normalized_path = "/".join(part for part in (path.strip("/"), "orders") if part)
            return urlunsplit(
                (
                    parsed.scheme or "https",
                    parsed.netloc,
                    f"/{normalized_path}",
                    "",
                    "",
                )
            )
        if value.endswith("/api/orders") or value.endswith("/orders"):
            return value
        if "market.loquieroaca.com" in value:
            return self._join_url(value, "/orders" if value.endswith("/api") else "/api/orders")
        if proxy:
            return self._join_url(value, "/orders" if value.endswith("/api") else "/api/orders")
        return self._join_url(value, "/orders")

    def _normalize_product(self, item):
        item = item if isinstance(item, dict) else {}
        raw_payload = item.get("raw_payload") if isinstance(item.get("raw_payload"), dict) else {}
        raw_images = raw_payload.get("images") if isinstance(raw_payload.get("images"), list) else []
        image = (
            item.get("image")
            or item.get("imageUrl")
            or item.get("thumbnail")
            or item.get("picture")
            or item.get("pictureUrl")
            or item.get("mainImage")
            or raw_payload.get("image")
            or raw_payload.get("imageUrl")
            or (raw_images[0] if raw_images else "")
            or ""
        )
        price = (
            item.get("price")
            or item.get("salePrice")
            or item.get("meliSalePrice")
            or item.get("listPrice")
            or item.get("amount")
            or raw_payload.get("price")
        )
        stock = (
            item.get("stock")
            if item.get("stock") is not None
            else item.get("stockQuantity")
            if item.get("stockQuantity") is not None
            else raw_payload.get("stock")
        )
        return {
            "id": item.get("_id") or item.get("id") or item.get("sku") or item.get("external_id") or item.get("externalId") or "",
            "sku": item.get("sku") or item.get("seller_sku") or item.get("sellerSku") or raw_payload.get("sellerSku") or "",
            "market_sku": item.get("market_sku") or item.get("marketSku") or raw_payload.get("marketSku") or "",
            "title": item.get("title") or item.get("name") or item.get("productName") or raw_payload.get("title") or "Sin titulo",
            "image": image,
            "price": self._as_float(price, None),
            "stock": self._as_int(stock, 0),
            "status": item.get("status") or item.get("publicationStatus") or "",
            "marketplace": item.get("marketplace") or "",
            "external_id": (
                item.get("external_id")
                or item.get("externalId")
                or item.get("marketplaceId")
                or item.get("itemId")
                or raw_payload.get("publicationId")
                or ""
            ),
            "publication_url": (
                item.get("publication_url")
                or item.get("publicationUrl")
                or item.get("link")
                or raw_payload.get("LinkPublicacion")
                or raw_payload.get("linkPublicacion")
                or ""
            ),
            "last_detected_at": (
                item.get("lastDetectedAt")
                or item.get("last_detection_at")
                or item.get("lastSeenAt")
                or item.get("last_seen_at")
                or item.get("updatedAt")
                or item.get("updated_at")
                or ""
            ),
        }

    def _normalize_product_summary(self, response):
        if not isinstance(response, dict):
            return {"status_map": {}, "total": 0}
        summary = response.get("summary") or {}
        status_map = (
            summary.get("statusMap")
            or summary.get("status_map")
            or response.get("statusMap")
            or response.get("status_map")
            or {}
        )
        statuses = summary.get("statuses") or []
        if not statuses and status_map:
            percentage_map = summary.get("statusPercentageMap") or {}
            statuses = [
                {
                    "status": status,
                    "total": self._as_int(total, 0),
                    "percentage": self._as_float(percentage_map.get(status), 0),
                }
                for status, total in status_map.items()
            ]
        return {
            "total": self._as_int(summary.get("total") or response.get("total"), 0),
            "status_map": status_map,
            "statuses": [
                {
                    "status": self._clean(item.get("status")),
                    "total": self._as_int(item.get("total"), 0),
                    "percentage": self._as_float(item.get("percentage"), 0),
                }
                for item in statuses
                if isinstance(item, dict) and self._clean(item.get("status"))
            ],
        }

    def _normalize_import_run(self, item):
        item = item if isinstance(item, dict) else {}
        status = item.get("status") or item.get("state") or ""
        processed = self._as_int(
            item.get("processed") or item.get("processedItems") or item.get("itemsProcessed"),
            0,
        )
        total = self._as_int(item.get("total") or item.get("totalItems"), 0)
        progress = self._as_float(item.get("progress") or item.get("progressPercent"), None)
        if progress is None and total:
            progress = round((processed / total) * 100, 2)
        return {
            "id": item.get("_id") or item.get("id") or item.get("runId") or "",
            "status": status,
            "marketplace": item.get("marketplace") or "",
            "started_at": item.get("started_at") or item.get("startedAt") or item.get("createdAt") or "",
            "finished_at": item.get("finished_at") or item.get("finishedAt") or "",
            "processed": processed,
            "total": total,
            "progress": progress,
            "message": item.get("message") or item.get("error") or item.get("errorMessage") or "",
        }

    def _normalize_status(self, response):
        status_map = (
            response.get("statusMap")
            or response.get("status_map")
            or response.get("statuses")
            or {}
        )
        percentage_map = (
            response.get("statusPercentageMap")
            or response.get("status_percentage_map")
            or response.get("percentages")
            or {}
        )
        total = self._as_int(response.get("total"), 0) or sum(
            self._as_int(value, 0) for value in status_map.values()
        )
        statuses = []
        for status, count in status_map.items():
            statuses.append(
                {
                    "status": status,
                    "count": self._as_int(count, 0),
                    "percentage": self._as_float(
                        percentage_map.get(status),
                        round((self._as_int(count, 0) / total) * 100, 2) if total else 0,
                    ),
                }
            )
        statuses.sort(key=lambda item: item["count"], reverse=True)
        return {
            "total": total,
            "statuses": statuses,
            "status_map": status_map,
            "status_percentage_map": percentage_map,
        }

    @staticmethod
    def _response_items(response):
        if isinstance(response, list):
            return response
        if not isinstance(response, dict):
            return []
        for key in ("items", "data", "products", "runs", "results"):
            value = response.get(key)
            if isinstance(value, list):
                return value
        return []

    @staticmethod
    def _response_order_items(response):
        if isinstance(response, list):
            return response
        if not isinstance(response, dict):
            return []
        for key in ("items", "orders", "data", "results"):
            value = response.get(key)
            if isinstance(value, list):
                return value
        return []

    @staticmethod
    def _extract_order_lines(item):
        for key in ("items", "orderItems", "order_items", "products", "lines"):
            value = item.get(key)
            if isinstance(value, list):
                return [line for line in value if isinstance(line, dict)]
        return []

    @staticmethod
    def _normalize_error(error):
        if isinstance(error, (dict, list)):
            return json.dumps(error, ensure_ascii=False)
        return str(error or "")

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    @staticmethod
    def _as_int(value, default=0):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _join_url(base, path):
        clean_base = str(base or "").rstrip("/")
        clean_path = str(path or "").lstrip("/")
        if not clean_path:
            return clean_base
        if not clean_base:
            return clean_path
        return "/".join([clean_base, clean_path])
