from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class LqaMercadolibreCatalogService(models.AbstractModel):
    _name = "lqa.mercadolibre.catalog.service"
    _description = "Servicio de catalogo MercadoLibre"

    DEFAULT_ENDPOINT = (
        "https://catalog-meli.loquieroaca.com/analytics/products/performance"
    )
    ALLOWED_FILTERS = {
        "search",
        "brand",
        "categoryId",
        "domainId",
        "status",
        "condition",
        "skuPrefix",
        "hasOrders",
        "hasVisits",
        "minOrders",
        "minRevenue",
        "createdFrom",
        "createdTo",
        "sortBy",
        "sortOrder",
        "limit",
        "offset",
    }
    BOOLEAN_FILTERS = {"hasOrders", "hasVisits"}

    @api.model
    def get_products(self, filters=None):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(_("No tenes permisos para consultar este catalogo."))

        params = self._prepare_params(filters or {})
        endpoint = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.mercadolibre_catalog_url",
                self.DEFAULT_ENDPOINT,
            )
        )
        if not endpoint:
            raise UserError(_("Configura la URL del catalogo MercadoLibre."))

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            endpoint,
            params=params,
        )
        products = response.get("products") or []

        return {
            "pagination": response.get("pagination") or {},
            "sort": response.get("sort") or {},
            "products": [self._normalize_product(product) for product in products],
        }

    def _prepare_params(self, filters):
        params = {}
        for key in self.ALLOWED_FILTERS:
            value = filters.get(key)
            if value is None or value == "":
                continue
            if key in self.BOOLEAN_FILTERS:
                value = str(value).lower()
                if value not in {"true", "false"}:
                    continue
            params[key] = value

        params["limit"] = min(max(self._as_int(params.get("limit"), 100), 1), 100)
        params["offset"] = max(self._as_int(params.get("offset"), 0), 0)
        params.setdefault("sortBy", "revenue")
        params.setdefault("sortOrder", "desc")
        return params

    @staticmethod
    def _as_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_product(product):
        result = dict(product)
        thumbnail = result.get("thumbnail") or ""
        if thumbnail.startswith("http://"):
            thumbnail = "https://" + thumbnail.removeprefix("http://")
        result["thumbnail"] = thumbnail
        return result
