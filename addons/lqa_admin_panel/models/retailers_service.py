import base64
import csv
import io
import json
import os
import posixpath
import re
import zipfile
from urllib.parse import quote, urlsplit, urlunsplit
from xml.etree import ElementTree

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaRetailersService(models.AbstractModel):
    _name = "lqa.retailers.service"
    _description = "Servicio de retailers y marketplaces"

    DEFAULT_MADRE_API_URL = "https://api.madre.loquieroaca.com"
    DEFAULT_PRODUCTS_API_URL = "https://api.products.loquieroaca.com"
    DEFAULT_ORDERS_PROXY_URL = "https://order.api.loquieroaca.com/orders"
    FRAVEGA_IMAGE_BASE_URL = "https://images.fravega.com"
    FRAVEGA_IMAGE_DEFAULT_SIZE = "f500"
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
    def get_marketplace_catalog(self, filters=None):
        self._check_access()
        filters = filters or {}
        limit = min(max(self._as_int(filters.get("limit"), 10), 1), 100)
        offset = max(self._as_int(filters.get("offset"), 0), 0)
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(
                self._madre_base_url(),
                "/api/internal/marketplace/products/items/marketplaces",
            ),
            params={"offset": offset, "limit": limit},
            timeout=self._timeout(),
        )
        payload = response if isinstance(response, dict) else {}
        items = self._response_items(response)
        total = self._as_int(payload.get("total"), len(items))
        count = self._as_int(payload.get("count"), len(items))
        has_next = bool(payload.get("hasNext"))
        next_offset = self._as_int(
            payload.get("nextOffset"),
            offset + limit,
        )
        return {
            "items": [
                self._normalize_marketplace_catalog_item(item)
                for item in items
            ],
            "pagination": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "count": count,
                "has_previous": offset > 0,
                "has_next": has_next,
                "next_offset": next_offset,
                "page": (offset // limit) + 1,
                "total_pages": max((total + limit - 1) // limit, 1),
            },
        }

    @api.model
    def get_marketplace_catalog_sku(self, seller_sku):
        self._check_access()
        seller_sku = self._clean(seller_sku)
        if not seller_sku:
            raise UserError(_("Ingresa un seller SKU para buscar."))
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(
                self._madre_base_url(),
                (
                    "/api/internal/marketplace/products/items/"
                    f"{quote(seller_sku, safe='')}/marketplaces"
                ),
            ),
            timeout=self._timeout(),
        )
        return self._normalize_marketplace_catalog_item(response)

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
            "items": [self._normalize_product(item, marketplace_id) for item in items],
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

    @api.model
    def refresh_published_sku(self, marketplace_id, sku):
        self._check_access()
        marketplace_id = self._validate_refresh_marketplace(marketplace_id)
        sku = self._clean(sku)
        if not sku:
            raise UserError(_("Ingresa un SKU para actualizar."))

        response = self.env["lqa.api.client"].request_absolute_json(
            "POST",
            self._join_url(
                self._products_base_url(),
                (
                    "/api/internal/marketplace-changes/refresh-published/"
                    f"{marketplace_id}/{quote(sku, safe='')}"
                ),
            ),
            timeout=self._timeout(),
        )
        return self._normalize_refresh_result(
            marketplace_id,
            response,
            action="sku",
            extra={"sku": sku, "sku_count": 1},
        )

    @api.model
    def refresh_published_bulk(self, marketplace_id, filename, content_base64, run_id=""):
        self._check_access()
        marketplace_id = self._validate_refresh_marketplace(marketplace_id)
        skus = self._parse_refresh_sku_file(filename, content_base64)
        run_id = self._clean(run_id) or self._default_refresh_run_id(marketplace_id)

        response = self.env["lqa.api.client"].request_absolute_json(
            "POST",
            self._join_url(
                self._products_base_url(),
                f"/api/internal/marketplace-changes/refresh-published/{marketplace_id}/bulk",
            ),
            payload={"runId": run_id, "skus": skus},
            timeout=self._timeout(),
        )
        return self._normalize_refresh_result(
            marketplace_id,
            response,
            action="bulk",
            extra={
                "run_id": run_id,
                "sku_count": len(skus),
                "filename": self._clean(filename),
            },
        )

    @api.model
    def get_paused_skus(self, filters=None):
        self._check_access()
        filters = filters or {}
        limit = min(max(self._as_int(filters.get("limit"), 100), 1), 500)
        offset = max(self._as_int(filters.get("offset"), 0), 0)
        params = {
            "limit": limit,
            "offset": offset,
        }
        sku = self._clean(filters.get("sku"))
        paused = self._clean(filters.get("paused")).lower()
        if sku:
            params["sku"] = sku
        if paused in ("true", "false"):
            params["paused"] = paused

        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(
                self._madre_base_url(),
                "/api/internal/marketplace/products/paused-skus",
            ),
            params=params,
            headers=self._madre_internal_headers(),
            timeout=self._timeout(),
        )
        payload = response if isinstance(response, dict) else {}
        items = self._response_items(response)
        total = self._as_int(payload.get("total"), len(items))
        count = self._as_int(payload.get("count"), len(items))
        has_next = (
            bool(payload.get("hasNext"))
            if "hasNext" in payload
            else offset + limit < total
        )
        next_offset = self._as_int(payload.get("nextOffset"), offset + limit)
        return {
            "items": [
                self._normalize_paused_sku(item, index)
                for index, item in enumerate(items)
            ],
            "pagination": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "count": count,
                "has_previous": offset > 0,
                "has_next": has_next,
                "next_offset": next_offset,
                "page": (offset // limit) + 1 if limit else 1,
            },
            "filters": {
                "sku": sku,
                "paused": paused,
            },
        }

    @api.model
    def delete_paused_sku(self, sku):
        self._check_access()
        sku = self._clean(sku)
        if not sku:
            raise UserError(_("Ingresa un SKU para eliminar."))
        response = self.env["lqa.api.client"].request_absolute_json(
            "DELETE",
            self._join_url(
                self._madre_base_url(),
                f"/api/internal/marketplace/products/paused-skus/{quote(sku, safe='')}",
            ),
            headers=self._madre_internal_headers(),
            timeout=self._timeout(),
        )
        payload = response if isinstance(response, dict) else {}
        return {
            "sku": self._clean(payload.get("sku")) or sku,
            "deleted": self._as_bool(payload.get("deleted"), True),
            "status": self._clean(payload.get("status") or payload.get("result") or "DELETED"),
            "message": self._clean(payload.get("message") or payload.get("detail")),
            "triggered_at": fields.Datetime.to_string(fields.Datetime.now()),
            "raw": payload,
        }

    @api.model
    def upsert_paused_skus_bulk(self, filename, content_base64, default_paused=True):
        self._check_access()
        items = self._parse_paused_sku_file(filename, content_base64, default_paused)
        response = self.env["lqa.api.client"].request_absolute_json(
            "PUT",
            self._join_url(
                self._madre_base_url(),
                "/api/internal/marketplace/products/paused-skus/bulk",
            ),
            payload={"items": items},
            headers=self._madre_internal_headers(),
            timeout=self._timeout(),
        )
        payload = response if isinstance(response, dict) else {}
        response_items = self._response_items(response)
        return {
            "status": self._clean(
                payload.get("status")
                or payload.get("state")
                or payload.get("result")
                or "UPDATED"
            ),
            "message": self._clean(
                payload.get("message")
                or payload.get("detail")
                or payload.get("description")
            ),
            "filename": self._clean(filename),
            "sku_count": len(items),
            "paused_count": sum(1 for item in items if item["paused"]),
            "active_count": sum(1 for item in items if not item["paused"]),
            "api_count": self._as_int(
                payload.get("count")
                or payload.get("total")
                or payload.get("updated")
                or payload.get("upserted"),
                len(response_items) or len(items),
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

    def _validate_refresh_marketplace(self, marketplace_id):
        marketplace_id = self._clean(marketplace_id).lower()
        if marketplace_id not in self.REFRESH_PUBLISHED_MARKETPLACES:
            raise UserError(_("Marketplace no disponible para actualizacion."))
        return marketplace_id

    def _normalize_refresh_result(self, marketplace_id, response, action="", extra=None):
        payload = response if isinstance(response, dict) else {}
        marketplace = self.MARKETPLACES.get(marketplace_id, {})
        result = {
            "action": action,
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
            "job_id": self._clean(
                payload.get("jobId")
                or payload.get("job_id")
                or payload.get("id")
            ),
            "triggered_at": fields.Datetime.to_string(fields.Datetime.now()),
            "raw": payload,
        }
        result.update(extra or {})
        return result

    def _default_refresh_run_id(self, marketplace_id):
        now = fields.Datetime.now()
        return f"refresh-{marketplace_id}-manual-{now.strftime('%Y%m%d%H%M%S')}"

    def _parse_refresh_sku_file(self, filename, content_base64):
        filename = self._clean(filename)
        if not filename:
            raise UserError(_("Selecciona un archivo con SKUs."))
        try:
            content = base64.b64decode(content_base64 or "", validate=True)
        except (TypeError, ValueError) as error:
            raise UserError(_("El archivo recibido no es valido.")) from error
        if not content:
            raise UserError(_("El archivo esta vacio."))

        extension = os.path.splitext(filename.lower())[1]
        if extension == ".csv":
            rows = self._read_csv_rows(content)
        elif extension == ".xlsx":
            rows = self._read_xlsx_rows(content)
        else:
            raise UserError(_("Usa un archivo CSV o Excel XLSX."))
        return self._skus_from_rows(rows)

    def _skus_from_rows(self, rows):
        clean_rows = [
            [self._clean(cell) for cell in row]
            for row in rows
            if any(self._clean(cell) for cell in row)
        ]
        if not clean_rows:
            raise UserError(_("El archivo no contiene SKUs."))

        headers = [self._normalize_header(cell) for cell in clean_rows[0]]
        sku_index = self._find_header_index(
            headers,
            {
                "sku",
                "sellerSku",
                "sellersku",
                "seller_sku",
                "seller",
                "asin",
            },
        )
        data_rows = clean_rows[1:] if sku_index >= 0 else clean_rows
        if sku_index < 0:
            sku_index = 0

        skus = []
        seen = set()
        for row in data_rows:
            sku = self._cell(row, sku_index)
            if not sku:
                continue
            normalized = sku.upper()
            if normalized in seen:
                continue
            seen.add(normalized)
            skus.append(sku)
        if not skus:
            raise UserError(_("No encontre SKUs validos en el archivo."))
        return skus

    def _parse_paused_sku_file(self, filename, content_base64, default_paused=True):
        filename = self._clean(filename)
        if not filename:
            raise UserError(_("Selecciona un archivo con SKUs."))
        try:
            content = base64.b64decode(content_base64 or "", validate=True)
        except (TypeError, ValueError) as error:
            raise UserError(_("El archivo recibido no es valido.")) from error
        if not content:
            raise UserError(_("El archivo esta vacio."))

        extension = os.path.splitext(filename.lower())[1]
        if extension == ".csv":
            rows = self._read_csv_rows(content)
        elif extension == ".xlsx":
            rows = self._read_xlsx_rows(content)
        else:
            raise UserError(_("Usa un archivo CSV o Excel XLSX."))
        return self._paused_items_from_rows(rows, default_paused)

    def _paused_items_from_rows(self, rows, default_paused=True):
        clean_rows = [
            [self._clean(cell) for cell in row]
            for row in rows
            if any(self._clean(cell) for cell in row)
        ]
        if not clean_rows:
            raise UserError(_("El archivo no contiene SKUs."))

        headers = [self._normalize_header(cell) for cell in clean_rows[0]]
        sku_index = self._find_header_index(
            headers,
            {
                "sku",
                "sellersku",
                "seller_sku",
                "seller",
                "asin",
            },
        )
        paused_index = self._find_header_index(
            headers,
            {
                "paused",
                "pausado",
                "pausada",
                "ispaused",
                "estado",
                "status",
            },
        )
        data_rows = clean_rows[1:] if sku_index >= 0 else clean_rows
        if sku_index < 0:
            sku_index = 0

        items = []
        seen = set()
        for row in data_rows:
            sku = self._cell(row, sku_index)
            if not sku:
                continue
            normalized = sku.upper()
            if normalized in seen:
                continue
            seen.add(normalized)
            paused = (
                self._parse_paused_value(self._cell(row, paused_index), default_paused)
                if paused_index >= 0
                else self._as_bool(default_paused, True)
            )
            items.append({"sku": sku, "paused": paused})
        if not items:
            raise UserError(_("No encontre SKUs validos en el archivo."))
        return items

    def _parse_paused_value(self, value, default=False):
        clean_value = self._clean(value).lower()
        if clean_value in ("paused", "pausado", "pausada", "true", "1", "si", "yes", "y"):
            return True
        if clean_value in ("active", "activo", "activa", "false", "0", "no", "n"):
            return False
        return self._as_bool(default, False)

    def _read_csv_rows(self, content):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel_tab if "\t" in sample else csv.excel
        return list(csv.reader(io.StringIO(text), dialect))

    def _read_xlsx_rows(self, content):
        try:
            workbook = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as error:
            raise UserError(_("El archivo XLSX no es valido.")) from error
        with workbook:
            shared_strings = self._xlsx_shared_strings(workbook)
            sheet_path = self._xlsx_first_sheet_path(workbook)
            if not sheet_path:
                raise UserError(_("El XLSX no contiene hojas."))
            try:
                sheet_root = ElementTree.fromstring(workbook.read(sheet_path))
            except (KeyError, ElementTree.ParseError) as error:
                raise UserError(_("No se pudo leer la primera hoja del XLSX.")) from error

        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows = []
        for row in sheet_root.findall(".//x:sheetData/x:row", namespace):
            values = {}
            max_column = -1
            for cell in row.findall("x:c", namespace):
                column = self._xlsx_column_index(cell.get("r", ""))
                if column < 0:
                    continue
                values[column] = self._xlsx_cell_value(cell, shared_strings, namespace)
                max_column = max(max_column, column)
            if max_column >= 0:
                rows.append([values.get(index, "") for index in range(max_column + 1)])
        return rows

    def _xlsx_shared_strings(self, workbook):
        path = "xl/sharedStrings.xml"
        if path not in workbook.namelist():
            return []
        try:
            root = ElementTree.fromstring(workbook.read(path))
        except ElementTree.ParseError:
            return []
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        return [
            "".join(node.text or "" for node in item.findall(".//x:t", namespace))
            for item in root.findall("x:si", namespace)
        ]

    def _xlsx_first_sheet_path(self, workbook):
        namespace = {
            "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "p": "http://schemas.openxmlformats.org/package/2006/relationships",
        }
        try:
            workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
            relationships_root = ElementTree.fromstring(
                workbook.read("xl/_rels/workbook.xml.rels")
            )
        except (KeyError, ElementTree.ParseError):
            return ""
        sheet = workbook_root.find("x:sheets/x:sheet", namespace)
        if sheet is None:
            return ""
        relationship_id = sheet.get(f"{{{namespace['r']}}}id")
        for relationship in relationships_root.findall("p:Relationship", namespace):
            if relationship.get("Id") == relationship_id:
                target = (relationship.get("Target") or "").lstrip("/")
                return (
                    target
                    if target.startswith("xl/")
                    else posixpath.normpath(f"xl/{target}")
                )
        return ""

    def _xlsx_cell_value(self, cell, shared_strings, namespace):
        cell_type = cell.get("t", "")
        if cell_type == "inlineStr":
            return "".join(
                node.text or "" for node in cell.findall(".//x:t", namespace)
            )
        value_node = cell.find("x:v", namespace)
        value = value_node.text if value_node is not None else ""
        if cell_type == "s":
            index = self._as_int(value, -1)
            return shared_strings[index] if 0 <= index < len(shared_strings) else ""
        if cell_type == "b":
            return "true" if value == "1" else "false"
        return value

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

    def _madre_internal_headers(self):
        params = self.env["ir.config_parameter"].sudo()
        token = (
            params.get_param("lqa_admin_panel.retailers_madre_api_token", "")
            or os.environ.get("LQA_RETAILERS_MADRE_API_TOKEN", "")
            or params.get_param("lqa_admin_panel.api_token", "")
            or os.environ.get("LQA_API_TOKEN", "")
        ).strip()
        if not token:
            raise UserError(_("Configura el token interno de Madre para Retailers."))
        return {"x-internal-api-key": token}

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

    def _as_dict(self, value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return {}
            try:
                parsed = json.loads(value)
            except ValueError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _normalize_product(self, item, marketplace_id=""):
        item = item if isinstance(item, dict) else {}
        raw_payload = self._as_dict(item.get("raw_payload") or item.get("rawPayload"))
        request_payload = self._as_dict(raw_payload.get("request"))
        response_payload = self._as_dict(raw_payload.get("response"))
        product_attributes = (
            raw_payload.get("productAttributes")
            if isinstance(raw_payload.get("productAttributes"), dict)
            else {}
        )
        item_attributes = (
            item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        )
        raw_attributes = (
            raw_payload.get("attributes")
            if isinstance(raw_payload.get("attributes"), dict)
            else {}
        )
        request_attributes = (
            request_payload.get("productAttributes")
            if isinstance(request_payload.get("productAttributes"), dict)
            else request_payload
        )
        response_attributes = (
            response_payload.get("productAttributes")
            if isinstance(response_payload.get("productAttributes"), dict)
            else {}
        )
        raw_product = (
            raw_payload.get("product")
            if isinstance(raw_payload.get("product"), dict)
            else {}
        )
        raw_product = self._as_dict(raw_product)
        raw_product_attributes = {}
        if isinstance(raw_product.get("productAttributes"), dict):
            raw_product_attributes = raw_product["productAttributes"]
        elif isinstance(raw_product.get("attributes"), dict):
            raw_product_attributes = raw_product["attributes"]
        offer = self._as_dict(
            item.get("offer")
            or raw_payload.get("offer")
            or item.get("googleOffer")
            or raw_payload.get("googleOffer")
        )
        offer_attributes = self._as_dict(
            offer.get("productAttributes") or offer.get("attributes")
        )
        image = self._first_product_image(
            item.get("image"),
            item.get("imageUrl"),
            item.get("image_url"),
            item.get("thumbnail"),
            item.get("thumbnailUrl"),
            item.get("thumbnail_url"),
            item.get("picture"),
            item.get("pictureUrl"),
            item.get("picture_url"),
            item.get("mainImage"),
            item.get("main_image"),
            item.get("imageLink"),
            item.get("image_link"),
            item.get("images"),
            item.get("additionalImageLinks"),
            item.get("additional_image_links"),
            item_attributes,
            product_attributes,
            raw_attributes,
            request_attributes,
            response_attributes,
            request_payload,
            response_payload,
            raw_product,
            raw_product_attributes,
            offer,
            offer_attributes,
            raw_payload.get("image"),
            raw_payload.get("imageUrl"),
            raw_payload.get("image_url"),
            raw_payload.get("thumbnail"),
            raw_payload.get("thumbnailUrl"),
            raw_payload.get("thumbnail_url"),
            raw_payload.get("picture"),
            raw_payload.get("pictureUrl"),
            raw_payload.get("picture_url"),
            raw_payload.get("mainImage"),
            raw_payload.get("main_image"),
            raw_payload.get("imageLink"),
            raw_payload.get("image_link"),
            raw_payload.get("images"),
            raw_payload.get("additionalImageLinks"),
            raw_payload.get("additional_image_links"),
            raw_payload.get("additionalImageUrls"),
            raw_payload.get("additional_image_urls"),
        )
        marketplace = item.get("marketplace") or raw_payload.get("marketplace") or marketplace_id or ""
        price = (
            item.get("price")
            or item.get("salePrice")
            or item.get("meliSalePrice")
            or item.get("listPrice")
            or item.get("amount")
            or raw_payload.get("price")
        )
        if isinstance(price, dict):
            amount_micros = price.get("amountMicros") or price.get("amount_micros")
            numeric_micros = self._as_float(amount_micros, None)
            price = (
                numeric_micros / 1000000
                if numeric_micros is not None
                else price.get("amount")
            )
        elif price in (None, "", 0, "0", "0.00") and isinstance(
            product_attributes.get("price"), dict
        ):
            amount_micros = (
                product_attributes["price"].get("amountMicros")
                or product_attributes["price"].get("amount_micros")
            )
            numeric_micros = self._as_float(amount_micros, None)
            price = (
                numeric_micros / 1000000
                if numeric_micros is not None
                else product_attributes["price"].get("amount")
            )
        elif price in (None, "", 0, "0", "0.00") and isinstance(
            response_attributes.get("price"), dict
        ):
            amount_micros = (
                response_attributes["price"].get("amountMicros")
                or response_attributes["price"].get("amount_micros")
            )
            numeric_micros = self._as_float(amount_micros, None)
            price = (
                numeric_micros / 1000000
                if numeric_micros is not None
                else response_attributes["price"].get("amount")
            )
        stock = (
            item.get("stock")
            if item.get("stock") is not None
            else item.get("stockQuantity")
            if item.get("stockQuantity") is not None
            else raw_payload.get("stock")
        )
        google_product_identity = self._parse_google_product_identity(
            item.get("name")
            or raw_payload.get("name")
            or item.get("external_id")
            or item.get("externalId")
            or ""
        )
        offer_id = self._clean(
            item.get("offerId")
            or item.get("offer_id")
            or raw_payload.get("offerId")
            or raw_payload.get("offer_id")
            or google_product_identity.get("offer_id")
        )
        content_language = self._clean(
            item.get("contentLanguage")
            or item.get("content_language")
            or raw_payload.get("contentLanguage")
            or raw_payload.get("content_language")
            or google_product_identity.get("content_language")
        )
        feed_label = self._clean(
            item.get("feedLabel")
            or item.get("feed_label")
            or raw_payload.get("feedLabel")
            or raw_payload.get("feed_label")
            or google_product_identity.get("feed_label")
        )
        google_product_key = (
            f"{content_language}~{feed_label}~{offer_id}"
            if offer_id and content_language and feed_label
            else ""
        )
        title = self._clean(
            item.get("title")
            or item.get("productTitle")
            or item.get("product_title")
            or item.get("name")
            or item.get("productName")
            or product_attributes.get("title")
            or product_attributes.get("headline")
            or raw_attributes.get("title")
            or request_attributes.get("title")
            or response_attributes.get("title")
            or request_payload.get("title")
            or response_payload.get("title")
            or raw_product_attributes.get("title")
            or raw_product.get("title")
            or raw_product.get("name")
            or offer_attributes.get("title")
            or offer.get("title")
            or raw_payload.get("title")
            or raw_payload.get("productTitle")
        )
        publication_url = self._normalize_product_url(
            item.get("publication_url")
            or item.get("publicationUrl")
            or item.get("publicationURL")
            or item.get("productUrl")
            or item.get("product_url")
            or item.get("link")
            or item.get("url")
            or product_attributes.get("link")
            or product_attributes.get("canonicalLink")
            or product_attributes.get("mobileLink")
            or raw_attributes.get("link")
            or request_attributes.get("link")
            or request_attributes.get("productUrl")
            or request_attributes.get("product_url")
            or request_payload.get("productUrl")
            or request_payload.get("product_url")
            or request_payload.get("link")
            or response_attributes.get("link")
            or response_attributes.get("canonicalLink")
            or response_attributes.get("mobileLink")
            or response_payload.get("link")
            or raw_product_attributes.get("link")
            or raw_product_attributes.get("canonicalLink")
            or raw_product_attributes.get("mobileLink")
            or raw_product.get("link")
            or raw_product.get("url")
            or offer_attributes.get("link")
            or offer_attributes.get("canonicalLink")
            or offer_attributes.get("mobileLink")
            or offer.get("link")
            or offer.get("url")
            or raw_payload.get("LinkPublicacion")
            or raw_payload.get("linkPublicacion")
            or raw_payload.get("publicationUrl")
            or raw_payload.get("productUrl")
            or raw_payload.get("link")
            or raw_payload.get("url")
        )
        item_id = (
            item.get("_id")
            or item.get("id")
            or item.get("sku")
            or item.get("external_id")
            or item.get("externalId")
            or ""
        )
        return {
            "id": item_id,
            "card_key": google_product_key or item_id,
            "sku": item.get("sku") or item.get("seller_sku") or item.get("sellerSku") or raw_payload.get("sellerSku") or "",
            "market_sku": item.get("market_sku") or item.get("marketSku") or raw_payload.get("marketSku") or "",
            "title": title or "Sin titulo",
            "image": self._normalize_product_image(marketplace, image),
            "price": self._as_float(price, None),
            "stock": self._as_int(stock, 0),
            "status": item.get("status") or item.get("publicationStatus") or "",
            "marketplace": marketplace,
            "external_id": (
                item.get("external_id")
                or item.get("externalId")
                or item.get("marketplaceId")
                or item.get("itemId")
                or raw_payload.get("publicationId")
                or ""
            ),
            "publication_url": publication_url,
            "last_detected_at": (
                item.get("lastDetectedAt")
                or item.get("last_detection_at")
                or item.get("lastSeenAt")
                or item.get("last_seen_at")
                or item.get("updatedAt")
                or item.get("updated_at")
                or ""
            ),
            "offer_id": offer_id,
            "content_language": content_language,
            "feed_label": feed_label,
            "google_product_key": google_product_key,
            "data_source": self._clean(
                item.get("dataSource")
                or item.get("data_source")
                or raw_payload.get("dataSource")
                or raw_payload.get("data_source")
            ),
        }

    def _normalize_paused_sku(self, item, index=0):
        item = item if isinstance(item, dict) else {"sku": item}
        sku = self._clean(
            item.get("sku")
            or item.get("sellerSku")
            or item.get("seller_sku")
            or item.get("sellerSKU")
            or item.get("asin")
            or item.get("id")
        )
        return {
            "key": self._clean(item.get("id")) or sku or f"paused-sku-{index}",
            "id": self._clean(item.get("id")),
            "sku": sku,
            "paused": self._as_bool(item.get("paused"), False),
            "status": self._clean(item.get("status") or item.get("state")),
            "reason": self._clean(item.get("reason") or item.get("message")),
            "created_at": self._clean(item.get("createdAt") or item.get("created_at")),
            "updated_at": self._clean(
                item.get("updatedAt")
                or item.get("updated_at")
                or item.get("lastSeenAt")
                or item.get("last_seen_at")
            ),
            "raw": item,
        }

    def _parse_google_product_identity(self, value):
        value = self._clean(value)
        if not value or "/products/" not in value:
            return {}
        product_name = value.rsplit("/products/", 1)[-1]
        parts = product_name.split("~", 2)
        if len(parts) != 3:
            return {}
        return {
            "content_language": self._clean(parts[0]),
            "feed_label": self._clean(parts[1]),
            "offer_id": self._clean(parts[2]),
        }

    def _first_product_image(self, *values):
        for value in values:
            image = self._extract_product_image_value(value)
            if image:
                return image
        return ""

    def _extract_product_image_value(self, value, allow_generic_url=False):
        if isinstance(value, (list, tuple)):
            for item in value:
                image = self._extract_product_image_value(
                    item,
                    allow_generic_url=True,
                )
                if image:
                    return image
            return ""

        if isinstance(value, dict):
            image_keys = (
                "image",
                "imageUrl",
                "image_url",
                "thumbnail",
                "thumbnailUrl",
                "thumbnail_url",
                "picture",
                "pictureUrl",
                "picture_url",
                "mainImage",
                "main_image",
                "imageLink",
                "image_link",
                "imageLinks",
                "image_links",
                "additionalImageLink",
                "additional_image_link",
                "additionalImageUrl",
                "additional_image_url",
            )
            for key in image_keys:
                image = self._extract_product_image_value(
                    value.get(key),
                    allow_generic_url=True,
                )
                if image:
                    return image

            list_keys = (
                "images",
                "additionalImageLinks",
                "additional_image_links",
                "additionalImageLink",
                "additional_image_link",
                "additionalImageUrls",
                "additional_image_urls",
                "additionalImageUrl",
                "additional_image_url",
                "media",
                "pictures",
            )
            for key in list_keys:
                image = self._extract_product_image_value(
                    value.get(key),
                    allow_generic_url=True,
                )
                if image:
                    return image

            container_keys = (
                "attributes",
                "productAttributes",
                "product_attributes",
                "product",
                "rawPayload",
                "raw_payload",
            )
            for key in container_keys:
                image = self._extract_product_image_value(value.get(key))
                if image:
                    return image

            if allow_generic_url:
                for key in ("url", "src", "path", "value"):
                    image = self._extract_product_image_value(value.get(key))
                    if image:
                        return image
            return ""

        return self._clean(value)

    def _normalize_product_url(self, value):
        if isinstance(value, dict):
            for key in (
                "link",
                "url",
                "href",
                "productUrl",
                "product_url",
                "publicationUrl",
                "publication_url",
                "canonicalLink",
                "mobileLink",
            ):
                url = self._normalize_product_url(value.get(key))
                if url:
                    return url
            return ""
        if isinstance(value, (list, tuple)):
            for item in value:
                url = self._normalize_product_url(item)
                if url:
                    return url
            return ""
        url = self._clean(value)
        if not url:
            return ""
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("www."):
            return f"https://{url}"
        if url.startswith("/"):
            return url
        return ""

    def _normalize_marketplace_catalog_item(self, item):
        item = item if isinstance(item, dict) else {}
        raw_items = item.get("items") if isinstance(item.get("items"), list) else []
        marketplaces = (
            item.get("marketplaces")
            if isinstance(item.get("marketplaces"), list)
            else []
        )
        price_map = (
            item.get("priceByMarketplace")
            if isinstance(item.get("priceByMarketplace"), dict)
            else {}
        )
        stock_map = (
            item.get("stockByMarketplace")
            if isinstance(item.get("stockByMarketplace"), dict)
            else {}
        )
        status_map = (
            item.get("statusByMarketplace")
            if isinstance(item.get("statusByMarketplace"), dict)
            else {}
        )
        normalized_items = [
            self._normalize_marketplace_catalog_detail(detail)
            for detail in raw_items
            if isinstance(detail, dict)
        ]
        detail_marketplaces = {
            detail["marketplace"]
            for detail in normalized_items
            if detail.get("marketplace")
        }
        for marketplace in marketplaces:
            marketplace = self._clean(marketplace).lower()
            if not marketplace or marketplace in detail_marketplaces:
                continue
            normalized_items.append(
                {
                    "marketplace": marketplace,
                    "marketplace_sku": "",
                    "external_id": "",
                    "price": self._as_float(price_map.get(marketplace), None),
                    "stock": self._as_int(stock_map.get(marketplace), 0),
                    "status": self._clean(status_map.get(marketplace)),
                    "is_active": False,
                    "last_seen_at": "",
                    "updated_at": "",
                }
            )
        normalized_marketplaces = []
        for marketplace in [
            *marketplaces,
            *(detail.get("marketplace") for detail in normalized_items),
        ]:
            marketplace = self._clean(marketplace).lower()
            if marketplace and marketplace not in normalized_marketplaces:
                normalized_marketplaces.append(marketplace)
        return {
            "seller_sku": self._clean(
                item.get("sellerSku")
                or item.get("seller_sku")
                or item.get("sku")
            ),
            "marketplaces": normalized_marketplaces,
            "items": normalized_items,
        }

    def _normalize_marketplace_catalog_detail(self, item):
        marketplace = self._clean(
            item.get("marketplace") or item.get("marketplaceId")
        ).lower()
        return {
            "marketplace": marketplace,
            "marketplace_sku": self._clean(
                item.get("marketplaceSku")
                or item.get("marketplace_sku")
            ),
            "external_id": self._clean(
                item.get("externalId")
                or item.get("external_id")
            ),
            "price": self._as_float(item.get("price"), None),
            "stock": self._as_int(item.get("stock"), 0),
            "status": self._clean(item.get("status")),
            "is_active": bool(item.get("isActive")),
            "last_seen_at": self._clean(
                item.get("lastSeenAt") or item.get("last_seen_at")
            ),
            "updated_at": self._clean(
                item.get("updatedAt") or item.get("updated_at")
            ),
        }

    def _normalize_product_image(self, marketplace_id, value):
        if isinstance(value, dict):
            value = self._extract_product_image_value(value, allow_generic_url=True)
        image = self._clean(value)
        if not image:
            return ""
        if image.startswith(("http://", "https://", "data:", "//")):
            return image
        if self._clean(marketplace_id).lower() != "fravega":
            return image

        image = image.lstrip("/")
        if image.startswith("images.fravega.com/"):
            return f"https://{image}"
        if "/" not in image:
            image = self._join_url(self.FRAVEGA_IMAGE_DEFAULT_SIZE, image)
        return self._join_url(self.FRAVEGA_IMAGE_BASE_URL, image)

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
            self._first_number(
                item,
                (
                    "items_processed",
                    "itemsProcessed",
                    "processed",
                    "processedItems",
                ),
            ),
            0,
        )
        failed = self._as_int(
            self._first_number(
                item,
                ("items_failed", "itemsFailed", "failed", "failedItems"),
            ),
            0,
        )
        batches = self._as_int(
            self._first_number(
                item,
                ("batches_processed", "batchesProcessed", "processedBatches"),
            ),
            0,
        )
        total = self._as_int(
            self._first_number(item, ("total", "totalItems", "items_total", "itemsTotal")),
            0,
        )
        progress = self._first_number(item, ("progress", "progressPercent"))
        if progress is None and total:
            progress = round((processed / total) * 100, 2)
        return {
            "id": item.get("_id") or item.get("id") or item.get("runId") or "",
            "status": status,
            "marketplace": item.get("marketplace") or "",
            "started_at": item.get("started_at") or item.get("startedAt") or item.get("createdAt") or "",
            "finished_at": item.get("finished_at") or item.get("finishedAt") or "",
            "processed": processed,
            "items_processed": processed,
            "items_failed": failed,
            "batches_processed": batches,
            "total": total,
            "progress": progress,
            "message": (
                item.get("message")
                or item.get("error_message")
                or item.get("error")
                or item.get("errorMessage")
                or ""
            ),
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
        for key in ("items", "data", "products", "runs", "results", "list", "records"):
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
    def _normalize_header(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())

    @staticmethod
    def _find_header_index(headers, candidates):
        normalized_candidates = {
            re.sub(r"[^a-z0-9]", "", str(candidate or "").strip().lower())
            for candidate in candidates
        }
        for index, header in enumerate(headers):
            if header in normalized_candidates:
                return index
        return -1

    @classmethod
    def _cell(cls, row, index):
        return cls._clean(row[index]) if index < len(row) else ""

    @staticmethod
    def _xlsx_column_index(reference):
        match = re.match(r"([A-Z]+)", str(reference or "").upper())
        if not match:
            return -1
        index = 0
        for character in match.group(1):
            index = index * 26 + ord(character) - ord("A") + 1
        return index - 1

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
    def _as_bool(value, default=False):
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        clean_value = str(value).strip().lower()
        if clean_value in ("true", "1", "yes", "y", "si", "s"):
            return True
        if clean_value in ("false", "0", "no", "n"):
            return False
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
