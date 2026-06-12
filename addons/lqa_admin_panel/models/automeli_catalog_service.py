from math import ceil

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class LqaAutomeliCatalogService(models.AbstractModel):
    _name = "lqa.automeli.catalog.service"
    _description = "Servicio de catalogo Automeli"

    DEFAULT_ENDPOINT = (
        "https://api.madre.loquieroaca.com/"
        "api/automeli/product-snapshots/all"
    )
    ALLOWED_FILTERS = {
        "limit",
        "offset",
        "mla",
        "sku",
        "totalPrice",
        "totalPriceMin",
        "totalPriceMax",
        "scrapedPrice",
        "scrapedPriceMin",
        "scrapedPriceMax",
        "stockQuantity",
        "stockQuantityMin",
        "stockQuantityMax",
        "amzStatus",
        "changed",
        "maxWeight",
        "maxWeightMin",
        "maxWeightMax",
        "meliSalePrice",
        "meliSalePriceMin",
        "meliSalePriceMax",
        "meliStatus",
        "listingTypeId",
        "subStatus",
        "appStatus",
        "createdAtFrom",
        "createdAtTo",
        "updatedAtFrom",
        "updatedAtTo",
    }
    INTEGER_FILTERS = {
        "limit",
        "offset",
        "stockQuantity",
        "stockQuantityMin",
        "stockQuantityMax",
        "maxWeight",
        "maxWeightMin",
        "maxWeightMax",
        "meliSalePrice",
        "meliSalePriceMin",
        "meliSalePriceMax",
        "appStatus",
    }
    FLOAT_FILTERS = {
        "totalPrice",
        "totalPriceMin",
        "totalPriceMax",
        "scrapedPrice",
        "scrapedPriceMin",
        "scrapedPriceMax",
    }
    DATETIME_FILTERS = {
        "createdAtFrom",
        "createdAtTo",
        "updatedAtFrom",
        "updatedAtTo",
    }

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
                "lqa_admin_panel.automeli_catalog_url",
                self.DEFAULT_ENDPOINT,
            )
        )
        if not endpoint:
            raise UserError(_("Configura la URL del catalogo Automeli."))

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            endpoint,
            params=params,
        )
        products = response.get("items") or []
        limit = self._as_int(response.get("limit"), params["limit"])
        offset = self._as_int(response.get("offset"), params["offset"])
        total = self._as_int(response.get("total"), len(products))
        count = self._as_int(response.get("count"), len(products))

        return {
            "products": products,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "count": count,
                "page": (offset // limit) + 1 if limit else 1,
                "total_pages": ceil(total / limit) if limit else 1,
                "has_next": bool(response.get("hasNext")),
                "has_previous": offset > 0,
                "next_offset": response.get("nextOffset"),
            },
        }

    def _prepare_params(self, filters):
        params = {}
        for key in self.ALLOWED_FILTERS:
            value = filters.get(key)
            if value is None or value == "":
                continue
            if key in self.INTEGER_FILTERS:
                value = self._as_int(value, None)
            elif key in self.FLOAT_FILTERS:
                value = self._as_float(value, None)
            elif key in self.DATETIME_FILTERS:
                value = self._normalize_datetime(value)
            if value is not None:
                params[key] = value

        params["limit"] = min(max(self._as_int(params.get("limit"), 50), 1), 50)
        params["offset"] = max(self._as_int(params.get("offset"), 0), 0)
        return params

    @staticmethod
    def _normalize_datetime(value):
        normalized = str(value).strip().replace("T", " ")
        if normalized and len(normalized) == 16:
            normalized += ":00"
        return normalized

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
