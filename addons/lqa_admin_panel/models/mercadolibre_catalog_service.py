import csv
import io
import json

from odoo import _, api, fields, models
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
    CSV_COLUMNS = (
        ("item_id", "mla", "item_id"),
        ("title", "titulo", "title"),
        ("sku", "sku", "sku"),
        ("brand", "marca", "brand"),
        ("status", "estado", "status"),
        ("condition", "condicion", "condition"),
        ("price", "precio", "price"),
        ("currency_id", "moneda", "currency_id"),
        ("available_quantity", "stock", "available_quantity"),
        ("revenue", "facturacion", "revenue"),
        ("orders_count", "ordenes", "orders_count"),
        ("units_sold", "unidades_vendidas", "units_sold"),
        ("total_visits", "visitas", "total_visits"),
        ("order_conversion_rate", "conversion_ordenes", "order_conversion_rate"),
        ("category_id", "categoria", "category_id"),
        ("domain_id", "dominio", "domain_id"),
        ("permalink", "link_publicacion", "permalink"),
        ("date_created", "fecha_creacion", "date_created"),
        ("last_updated", "ultima_actualizacion", "last_updated"),
        ("catalog_sold_quantity", "ventas_catalogo", "catalog_sold_quantity"),
        ("avg_ticket", "ticket_promedio", "avg_ticket"),
        ("first_order_date", "primera_orden", "first_order_date"),
        ("last_order_date", "ultima_orden", "last_order_date"),
        ("unit_conversion_rate", "conversion_unidades", "unit_conversion_rate"),
    )
    DEFAULT_CSV_COLUMNS = (
        "item_id",
        "title",
        "sku",
        "status",
        "price",
        "available_quantity",
        "permalink",
    )

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

    @api.model
    def get_selection_folders(self):
        self._check_access()
        folders = self.env["lqa.mercadolibre.selection.folder"].search(
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
        folder = self.env["lqa.mercadolibre.selection.folder"].create(
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

        line_model = self.env["lqa.mercadolibre.selection.item"]
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
            "folder": self._folder_to_dict(folder),
            "added": added,
            "updated": updated,
            "total": added + updated,
        }

    @api.model
    def get_selection_products(self, folder_id, limit=200, offset=0):
        self._check_access()
        folder = self._get_folder(folder_id)
        limit = min(max(self._as_int(limit, 200), 1), 1000)
        offset = max(self._as_int(offset, 0), 0)
        domain = [("folder_id", "=", folder.id)]
        lines = self.env["lqa.mercadolibre.selection.item"].search(
            domain,
            limit=limit,
            offset=offset,
            order="write_date desc, id desc",
        )
        total = self.env["lqa.mercadolibre.selection.item"].search_count(domain)
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
        line = self.env["lqa.mercadolibre.selection.item"].browse(
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
        if (
            not self.env.user.has_group("lqa_admin_panel.group_lqa_admin")
            and folder.create_uid != self.env.user
        ):
            raise AccessError(_("Solo podes eliminar carpetas creadas por tu usuario."))
        folder.unlink()
        return {"deleted": True}

    @api.model
    def export_selection_folder_csv(self, folder_id, columns=None):
        self._check_access()
        folder = self._get_folder(folder_id)
        column_map = {column[0]: column for column in self.CSV_COLUMNS}
        requested_columns = [
            self._clean(column)
            for column in (columns or [])
            if self._clean(column) in column_map
        ]
        if not requested_columns:
            requested_columns = list(self.DEFAULT_CSV_COLUMNS)

        lines = self.env["lqa.mercadolibre.selection.item"].search(
            [("folder_id", "=", folder.id)],
            order="id",
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([column_map[key][1] for key in requested_columns])
        for line in lines:
            writer.writerow(
                [
                    self._csv_value(getattr(line, column_map[key][2], ""))
                    for key in requested_columns
                ]
            )
        return {
            "filename": f"{self._csv_safe_name(folder.name)}-mercadolibre.csv",
            "content": buffer.getvalue(),
            "count": len(lines),
            "columns": requested_columns,
        }

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(_("No tenes permisos para consultar este catalogo."))

    def _get_folder(self, folder_id):
        folder = self.env["lqa.mercadolibre.selection.folder"].browse(
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
            "item_id": self._clean(self._first(product, "item_id", "itemId")),
            "title": self._clean(self._first(product, "title")),
            "thumbnail": self._clean(self._first(product, "thumbnail")),
            "status": self._clean(self._first(product, "status")),
            "brand": self._clean(self._first(product, "brand")),
            "sku": self._clean(self._first(product, "sku")),
            "condition": self._clean(self._first(product, "condition")),
            "price": self._as_float(self._first(product, "price"), 0),
            "currency_id": self._clean(
                self._first(product, "currency_id", "currencyId")
            ),
            "available_quantity": self._as_int(
                self._first(product, "available_quantity", "availableQuantity"), 0
            ),
            "revenue": self._as_float(self._first(product, "revenue"), 0),
            "orders_count": self._as_int(
                self._first(product, "orders_count", "ordersCount"), 0
            ),
            "units_sold": self._as_int(
                self._first(product, "units_sold", "unitsSold"), 0
            ),
            "total_visits": self._as_int(
                self._first(product, "total_visits", "totalVisits"), 0
            ),
            "order_conversion_rate": self._as_float(
                self._first(product, "order_conversion_rate", "orderConversionRate"),
                0,
            ),
            "category_id": self._clean(
                self._first(product, "category_id", "categoryId")
            ),
            "domain_id": self._clean(self._first(product, "domain_id", "domainId")),
            "permalink": self._clean(self._first(product, "permalink")),
            "date_created": self._clean(
                self._first(product, "date_created", "dateCreated")
            ),
            "last_updated": self._clean(
                self._first(product, "last_updated", "lastUpdated")
            ),
            "catalog_sold_quantity": self._as_int(
                self._first(product, "catalog_sold_quantity", "catalogSoldQuantity"),
                0,
            ),
            "avg_ticket": self._as_float(
                self._first(product, "avg_ticket", "avgTicket"),
                0,
            ),
            "first_order_date": self._clean(
                self._first(product, "first_order_date", "firstOrderDate")
            ),
            "last_order_date": self._clean(
                self._first(product, "last_order_date", "lastOrderDate")
            ),
            "unit_conversion_rate": self._as_float(
                self._first(product, "unit_conversion_rate", "unitConversionRate"),
                0,
            ),
            "payload_json": json.dumps(product, ensure_ascii=False),
        }

    def _product_key(self, product):
        parts = [
            self._clean(self._first(product, "item_id", "itemId")),
            self._clean(self._first(product, "sku")),
            self._clean(self._first(product, "permalink")),
        ]
        return "|".join(part for part in parts if part)

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
    def _as_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    @staticmethod
    def _first(source, *keys):
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return value
        return ""

    @staticmethod
    def _csv_value(value):
        if value is None or value is False:
            return ""
        return value

    def _csv_safe_name(self, value):
        clean_value = self._clean(value).lower().replace(" ", "-")
        return "".join(
            character
            for character in clean_value
            if character.isalnum() or character in {"-", "_"}
        ) or "mercadolibre-seleccion"

    @staticmethod
    def _normalize_product(product):
        result = dict(product)
        thumbnail = result.get("thumbnail") or ""
        if thumbnail.startswith("http://"):
            thumbnail = "https://" + thumbnail.removeprefix("http://")
        result["thumbnail"] = thumbnail
        return result
