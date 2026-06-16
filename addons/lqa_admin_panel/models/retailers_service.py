from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class LqaRetailersService(models.AbstractModel):
    _name = "lqa.retailers.service"
    _description = "Servicio de retailers y marketplaces"

    DEFAULT_MADRE_API_URL = "https://api.madre.loquieroaca.com"
    DEFAULT_PRODUCTS_API_URL = "https://api.madre.loquieroaca.com"
    DEFAULT_TIMEOUT_SECONDS = 60
    MARKETPLACES = {
        "google-merchant": {
            "name": "Google Merchant",
            "description": "Feed y publicaciones para Google Merchant Center.",
            "accent": "google",
        },
        "fravega": {
            "name": "Fravega",
            "description": "Catalogo, stock y precios publicados en Fravega.",
            "accent": "fravega",
        },
        "oncity": {
            "name": "OnCity",
            "description": "Publicaciones y sincronizaciones para OnCity.",
            "accent": "oncity",
        },
        "megatone": {
            "name": "Megatone",
            "description": "Productos, importaciones y estados de Megatone.",
            "accent": "megatone",
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
            params["status"] = status.upper()

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(self._madre_base_url(), "/api/internal/marketplace/products/items/all"),
            params=params,
            timeout=self._timeout(),
        )
        items = self._response_items(response)
        total = self._as_int(response.get("total"), len(items)) if isinstance(response, dict) else len(items)
        return {
            "items": [self._normalize_product(item) for item in items],
            "summary": self._normalize_product_summary(response),
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
                self.DEFAULT_MADRE_API_URL,
            )
            or self.DEFAULT_MADRE_API_URL
        ).strip()

    def _products_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param(
                "lqa_admin_panel.retailers_products_api_url",
                self.DEFAULT_PRODUCTS_API_URL,
            )
            or self.DEFAULT_PRODUCTS_API_URL
        ).strip()

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

    def _normalize_product(self, item):
        item = item if isinstance(item, dict) else {}
        image = (
            item.get("image")
            or item.get("imageUrl")
            or item.get("thumbnail")
            or item.get("picture")
            or item.get("pictureUrl")
            or item.get("mainImage")
            or ""
        )
        price = (
            item.get("price")
            or item.get("salePrice")
            or item.get("meliSalePrice")
            or item.get("listPrice")
            or item.get("amount")
        )
        stock = item.get("stock") if item.get("stock") is not None else item.get("stockQuantity")
        return {
            "id": item.get("_id") or item.get("id") or item.get("sku") or item.get("externalId") or "",
            "sku": item.get("sku") or item.get("sellerSku") or "",
            "title": item.get("title") or item.get("name") or item.get("productName") or "Sin titulo",
            "image": image,
            "price": self._as_float(price, None),
            "stock": self._as_int(stock, 0),
            "status": item.get("status") or item.get("publicationStatus") or "",
            "marketplace": item.get("marketplace") or "",
            "external_id": item.get("externalId") or item.get("marketplaceId") or item.get("itemId") or "",
            "last_detected_at": (
                item.get("lastDetectedAt")
                or item.get("last_detection_at")
                or item.get("lastSeenAt")
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
        return {
            "total": self._as_int(summary.get("total") or response.get("total"), 0),
            "status_map": status_map,
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
        return "/".join([str(base or "").rstrip("/"), str(path or "").lstrip("/")])
