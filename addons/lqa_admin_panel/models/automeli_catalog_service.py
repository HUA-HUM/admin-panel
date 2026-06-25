import json
import csv
import io
from math import ceil

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaAutomeliCatalogService(models.AbstractModel):
    _name = "lqa.automeli.catalog.service"
    _description = "Servicio de catalogo Automeli"

    DEFAULT_ENDPOINT = (
        "https://api.madre.loquieroaca.com/"
        "api/automeli/product-snapshots/all"
    )
    DEFAULT_STATUS_ENDPOINT = (
        "https://api.madre.loquieroaca.com/"
        "api/automeli/product-snapshots/last-updated"
    )
    MAX_FILTER_SELECTION_ROWS = 10000
    ALLOWED_FILTERS = {
        "limit",
        "offset",
        "mla",
        "sku",
        "brand",
        "title",
        "manufacturingTime",
        "pauseReason",
        "pausedSinceFrom",
        "pausedSinceTo",
        "totalPrice",
        "totalPriceMin",
        "totalPriceMax",
        "scrapedPrice",
        "scrapedPriceMin",
        "scrapedPriceMax",
        "shippingCost",
        "shippingCostMin",
        "shippingCostMax",
        "taxes",
        "taxesMin",
        "taxesMax",
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
        "discountTotalPrice",
        "discountTotalPriceMin",
        "discountTotalPriceMax",
        "meliStatus",
        "listingTypeId",
        "subStatus",
        "appStatus",
        "idMeliMainVariant",
        "image",
        "imageChanged",
        "imageChangedUrl",
        "permalink",
        "meliCategoryName",
        "meliMainCategory",
        "shippingFrom",
        "taxCategoryId",
        "createUsingPublisher",
        "dateUpdatedFrom",
        "dateUpdatedTo",
        "dateUpdatedMeliFrom",
        "dateUpdatedMeliTo",
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
        "meliSalePrice",
        "meliSalePriceMin",
        "meliSalePriceMax",
        "appStatus",
        "imageChanged",
        "taxCategoryId",
        "createUsingPublisher",
    }
    FLOAT_FILTERS = {
        "totalPrice",
        "totalPriceMin",
        "totalPriceMax",
        "scrapedPrice",
        "scrapedPriceMin",
        "scrapedPriceMax",
        "shippingCost",
        "shippingCostMin",
        "shippingCostMax",
        "taxes",
        "taxesMin",
        "taxesMax",
        "maxWeight",
        "maxWeightMin",
        "maxWeightMax",
        "discountTotalPrice",
        "discountTotalPriceMin",
        "discountTotalPriceMax",
    }
    DATETIME_FILTERS = {
        "pausedSinceFrom",
        "pausedSinceTo",
        "dateUpdatedFrom",
        "dateUpdatedTo",
        "dateUpdatedMeliFrom",
        "dateUpdatedMeliTo",
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

    @api.model
    def get_catalog_status(self):
        self._check_access()
        endpoint = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.automeli_catalog_status_url",
                self.DEFAULT_STATUS_ENDPOINT,
            )
        )
        if not endpoint:
            raise UserError(_("Configura la URL de estado del catalogo Automeli."))

        response = self.env["lqa.api.client"].request_absolute_json("GET", endpoint)
        response = response if isinstance(response, dict) else {}
        return {
            "total": self._as_int(response.get("total"), 0),
            "lastCreatedAt": response.get("lastCreatedAt") or "",
            "lastUpdatedAt": response.get("lastUpdatedAt") or "",
        }

    @api.model
    def get_selection_folders(self):
        self._check_access()
        folders = self.env["lqa.automeli.selection.folder"].search(
            [("active", "=", True)],
            order="write_date desc, id desc",
        )
        return [self._folder_to_dict(folder) for folder in folders]

    @api.model
    def create_selection_folder(self, name, description=False):
        self._check_access()
        name = str(name or "").strip()
        if not name:
            raise UserError(_("Indica un nombre para la carpeta."))
        folder = self.env["lqa.automeli.selection.folder"].create(
            {
                "name": name,
                "description": str(description or "").strip(),
            }
        )
        return self._folder_to_dict(folder)

    @api.model
    def save_products_to_folder(self, folder_id, products):
        self._check_access()
        folder = self._get_folder(folder_id)
        if not isinstance(products, list) or not products:
            raise UserError(_("Selecciona al menos un producto."))

        result = self._save_product_batch(folder, products)
        return {
            "folder": self._folder_to_dict(folder),
            **result,
        }

    @api.model
    def save_filtered_products_to_folder(self, folder_id, filters=None):
        self._check_access()
        folder = self._get_folder(folder_id)
        products, total = self._fetch_filtered_products(filters or {})
        if not products:
            raise UserError(_("El filtro actual no devolvio productos para guardar."))
        result = self._save_product_batch(folder, products)
        return {
            "folder": self._folder_to_dict(folder),
            "matched": total,
            **result,
        }

    def _save_product_batch(self, folder, products):
        line_model = self.env["lqa.automeli.selection.item"]
        added = 0
        updated = 0
        for product in products:
            values = self._selection_values_from_product(folder, product)
            existing = line_model.search(
                [
                    ("folder_id", "=", folder.id),
                    ("product_key", "=", values["product_key"]),
                ],
                limit=1,
            )
            if existing:
                existing.write(values)
                updated += 1
            else:
                line_model.create(values)
                added += 1

        return {
            "added": added,
            "updated": updated,
            "total": added + updated,
        }

    def _fetch_filtered_products(self, filters):
        filters = dict(filters or {})
        filters["offset"] = 0
        filters["limit"] = 50
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

        products = []
        seen = set()
        total = 0
        while True:
            params = self._prepare_params(filters)
            response = self.env["lqa.api.client"].request_absolute_json(
                "GET",
                endpoint,
                params=params,
            )
            page_products = response.get("items") or []
            total = self._as_int(response.get("total"), total or 0)
            if total > self.MAX_FILTER_SELECTION_ROWS:
                raise UserError(
                    _(
                        "El filtro devuelve %s productos. Refiná el filtro o baja el total a %s para guardar en carpeta."
                    )
                    % (total, self.MAX_FILTER_SELECTION_ROWS)
                )
            for product in page_products:
                key = self._product_key(product)
                if key and key not in seen:
                    seen.add(key)
                    products.append(product)
            if not page_products or not response.get("hasNext"):
                break
            next_offset = response.get("nextOffset")
            fallback_offset = self._as_int(params.get("offset"), 0) + self._as_int(
                params.get("limit"), 50
            )
            filters["offset"] = (
                self._as_int(next_offset, fallback_offset)
                if next_offset is not None
                else fallback_offset
            )
            if len(products) >= self.MAX_FILTER_SELECTION_ROWS:
                break
        return products, total or len(products)

    @api.model
    def get_selection_products(self, folder_id, limit=200, offset=0):
        self._check_access()
        folder = self._get_folder(folder_id)
        limit = min(max(self._as_int(limit, 200), 1), 500)
        offset = max(self._as_int(offset, 0), 0)
        domain = [("folder_id", "=", folder.id)]
        lines = self.env["lqa.automeli.selection.item"].search(
            domain,
            limit=limit,
            offset=offset,
            order="write_date desc, id desc",
        )
        total = self.env["lqa.automeli.selection.item"].search_count(domain)
        return {
            "folder": self._folder_to_dict(folder),
            "products": [line.to_panel_dict() for line in lines],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "count": len(lines),
                "has_next": offset + limit < total,
                "has_previous": offset > 0,
            },
        }

    @api.model
    def remove_selection_product(self, line_id):
        self._check_access()
        line = self.env["lqa.automeli.selection.item"].browse(
            self._as_int(line_id, 0)
        ).exists()
        if not line:
            raise UserError(_("El producto guardado no existe."))
        folder = line.folder_id
        line.unlink()
        return self._folder_to_dict(folder)

    @api.model
    def delete_selection_folder(self, folder_id):
        self._check_access()
        folder = self._get_folder(folder_id)
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_admin") and folder.create_uid != self.env.user:
            raise AccessError(_("Solo podes eliminar carpetas creadas por tu usuario."))
        folder.unlink()
        return {"deleted": True}

    @api.model
    def export_selection_folder_mlas(self, folder_id):
        self._check_access()
        folder = self._get_folder(folder_id)
        lines = self.env["lqa.automeli.selection.item"].search(
            [("folder_id", "=", folder.id)],
            order="id",
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["mla"])
        exported = set()
        for line in lines:
            if line.mla and line.mla not in exported:
                exported.add(line.mla)
                writer.writerow([line.mla])
        return {
            "filename": f"{self._csv_safe_name(folder.name)}-mlas.csv",
            "content": buffer.getvalue(),
            "count": len(exported),
        }

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(_("No tenes permisos para consultar este catalogo."))

    def _get_folder(self, folder_id):
        folder = self.env["lqa.automeli.selection.folder"].browse(
            self._as_int(folder_id, 0)
        ).exists()
        if not folder:
            raise UserError(_("La carpeta no existe."))
        return folder

    def _folder_to_dict(self, folder):
        return {
            "id": folder.id,
            "name": folder.name,
            "description": folder.description or "",
            "productCount": folder.product_count,
            "creatorName": folder.create_uid.name or "",
            "creatorLogin": folder.create_uid.login or "",
            "createdAt": fields.Datetime.to_string(folder.create_date),
            "updatedAt": fields.Datetime.to_string(folder.write_date),
            "canDelete": (
                self.env.user.has_group("lqa_admin_panel.group_lqa_admin")
                or folder.create_uid == self.env.user
            ),
        }

    def _selection_values_from_product(self, folder, product):
        product = product if isinstance(product, dict) else {}
        product_key = self._product_key(product)
        if not product_key:
            raise UserError(_("Hay un producto seleccionado sin MLA ni SKU."))
        return {
            "folder_id": folder.id,
            "product_key": product_key,
            "mla": self._clean(product.get("mla")),
            "sku": self._clean(product.get("sku")),
            "listing_type_id": self._clean(product.get("listingTypeId")),
            "meli_status": self._clean(product.get("meliStatus")),
            "amz_status": self._clean(product.get("amzStatus")),
            "total_price": self._as_float(product.get("totalPrice"), 0),
            "scraped_price": self._as_float(product.get("scrapedPrice"), 0),
            "meli_sale_price": self._as_float(product.get("meliSalePrice"), 0),
            "stock_quantity": self._as_int(product.get("stockQuantity"), 0),
            "max_weight": self._as_int(product.get("maxWeight"), 0),
            "changed": self._clean(product.get("changed")),
            "sub_status": self._clean(product.get("subStatus")),
            "app_status": self._clean(product.get("appStatus")),
            "snapshot_created_at": self._clean(product.get("createdAt")),
            "snapshot_updated_at": self._clean(product.get("updatedAt")),
            "payload_json": json.dumps(product, ensure_ascii=False),
        }

    def _product_key(self, product):
        parts = [
            self._clean(product.get("mla")),
            self._clean(product.get("sku")),
            self._clean(product.get("listingTypeId")),
        ]
        return "|".join(part for part in parts if part)

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

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    def _csv_safe_name(self, value):
        clean_value = self._clean(value).lower().replace(" ", "-")
        return "".join(
            character
            for character in clean_value
            if character.isalnum() or character in {"-", "_"}
        ) or "automeli-seleccion"
