import base64
import csv
import io
import os
import posixpath
import re
import zipfile
from urllib.parse import quote
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LqaRetailersPublisherService(models.AbstractModel):
    _name = "lqa.retailers.publisher.service"
    _description = "Servicio del publicador de retailers"

    FOLDERS_PATH = "/api/analytics/marketplace-favorites/marketplaces"
    BULK_PRODUCTS_PATH = "/api/analytics/marketplace-favorites/bulk"
    FAVORITES_PATH = "/api/analytics/marketplace-favorites/{folder_id}/favorites"
    EXECUTE_PUBLICATION_PATH = "/api/publications/execute/run"
    PUBLICATION_RUN_JOBS_PATH = "/api/publication-jobs/{run_id}/jobs"
    PENDING_PUBLICATIONS_PATH = "/api/publication-jobs/pending"
    PUBLICATION_MARKETPLACES = ("fravega", "megatone", "oncity")
    MAX_IMPORT_ROWS = 10000
    MAX_UPLOAD_BYTES = 20 * 1024 * 1024
    MAX_XLSX_XML_BYTES = 40 * 1024 * 1024
    BULK_BATCH_SIZE = 500
    PRODUCT_ID_HEADERS = {
        "productid",
        "product",
        "mla",
        "idproducto",
        "idpublicacion",
    }
    SELLER_SKU_HEADERS = {
        "sellersku",
        "sku",
        "skuventa",
        "sellerid",
    }
    PRODUCT_FILTERS = {
        "brand",
        "categoryId",
        "minPrice",
        "maxPrice",
        "minStock",
        "maxStock",
        "minVisits",
        "maxVisits",
        "minOrders",
        "maxOrders",
        "sortBy",
        "sortOrder",
    }

    @api.model
    def get_folders(self):
        self._check_access()
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(self._madre_base_url(), self.FOLDERS_PATH),
            headers=self._madre_headers(),
            timeout=self._timeout(),
        )
        return [
            self._normalize_folder(folder)
            for folder in self._extract_list(
                response,
                ("marketplaces", "folders", "items", "data", "results"),
            )
        ]

    @api.model
    def create_folder(self, name):
        self._check_access()
        name = self._clean(name)
        if not name:
            raise UserError(_("Ingresa un nombre para la carpeta."))
        if len(name) > 120:
            raise UserError(_("El nombre de la carpeta no puede superar 120 caracteres."))

        response = self.env["lqa.api.client"].request_absolute_json(
            "POST",
            self._join_url(self._madre_base_url(), self.FOLDERS_PATH),
            payload={"name": name},
            headers=self._madre_headers(),
            timeout=self._timeout(),
        )
        folder_payload = self._extract_record(
            response,
            ("marketplace", "folder", "item", "data", "result"),
        )
        if not folder_payload:
            folder_payload = {"name": name}
        return self._normalize_folder(folder_payload)

    @api.model
    def get_folder_products(self, folder_id, filters=None):
        self._check_access()
        folder_id = self._normalize_folder_id(folder_id)
        params = self._prepare_product_filters(filters or {})
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._favorites_url(folder_id),
            params=params,
            headers=self._madre_headers(),
            timeout=self._timeout(),
        )
        items = self._extract_list(
            response,
            ("favorites", "products", "items", "data", "results"),
        )
        response_dict = response if isinstance(response, dict) else {}
        pagination = self._extract_pagination(response)
        page = self._as_int(
            pagination.get("page")
            or pagination.get("currentPage")
            or response_dict.get("page"),
            params["page"],
        )
        limit = self._as_int(
            pagination.get("limit")
            or pagination.get("perPage")
            or pagination.get("pageSize")
            or response_dict.get("limit"),
            params["limit"],
        )
        total = self._as_int(
            pagination.get("total")
            or pagination.get("totalItems")
            or response_dict.get("total"),
            len(items),
        )
        total_pages = self._as_int(
            pagination.get("totalPages")
            or pagination.get("pages")
            or response_dict.get("totalPages"),
            0,
        )
        if not total_pages:
            total_pages = max((total + limit - 1) // limit, 1) if limit else 1

        return {
            "products": [self._normalize_favorite(item) for item in items],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "has_previous": page > 1,
                "has_next": page < total_pages,
            },
        }

    @api.model
    def add_products(self, folder_id, products):
        self._check_access()
        folder_id = self._normalize_folder_id(folder_id)
        normalized_products = self._normalize_products(products)
        return self._send_products(folder_id, normalized_products)

    @api.model
    def import_products(self, folder_id, filename, content_base64):
        self._check_access()
        folder_id = self._normalize_folder_id(folder_id)
        products = self._parse_import_file(filename, content_base64)
        result = self._send_products(folder_id, products)
        result["filename"] = self._clean(filename)
        return result

    @api.model
    def delete_products(self, folder_id, product_ids):
        self._check_access()
        folder_id = self._normalize_folder_id(folder_id)
        normalized_ids = []
        seen = set()
        for product_id in product_ids or []:
            product_id = self._clean(product_id)
            if not product_id or product_id in seen:
                continue
            seen.add(product_id)
            normalized_ids.append(product_id)
        if not normalized_ids:
            raise UserError(_("Selecciona al menos un producto para eliminar."))

        batches = 0
        for offset in range(0, len(normalized_ids), self.BULK_BATCH_SIZE):
            batch = normalized_ids[offset : offset + self.BULK_BATCH_SIZE]
            self.env["lqa.api.client"].request_absolute_json(
                "DELETE",
                self._favorites_url(folder_id),
                payload={"productIds": batch},
                headers=self._madre_headers(),
                timeout=self._timeout(),
            )
            batches += 1
        return {
            "folder_id": folder_id,
            "count": len(normalized_ids),
            "batches": batches,
        }

    @api.model
    def download_import_template(self):
        self._check_access()
        content = self._build_template_xlsx()
        return {
            "filename": "retailers-publicador-productos.xlsx",
            "content": base64.b64encode(content).decode("ascii"),
            "mimetype": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        }

    @api.model
    def execute_publication(self, folder_id, marketplaces):
        self._check_access()
        folder_id = self._normalize_folder_id(folder_id)
        normalized_marketplaces = []
        for marketplace in marketplaces or []:
            marketplace = self._clean(marketplace).lower()
            if (
                marketplace in self.PUBLICATION_MARKETPLACES
                and marketplace not in normalized_marketplaces
            ):
                normalized_marketplaces.append(marketplace)
        if not normalized_marketplaces:
            raise UserError(_("Selecciona al menos un marketplace para publicar."))

        response = self.env["lqa.api.client"].request_absolute_json(
            "POST",
            self._join_url(
                self._products_base_url(),
                self.EXECUTE_PUBLICATION_PATH,
            ),
            payload={
                "marketplaces": normalized_marketplaces,
                "folderId": folder_id,
            },
            timeout=self._timeout(),
        )
        payload = self._extract_record(
            response,
            ("run", "publicationRun", "data", "result"),
        )
        payload = self._extract_record(
            payload,
            ("run", "publicationRun", "data", "result"),
        )
        return {
            "run_id": self._clean(
                self._first(
                    payload,
                    "runId",
                    "publicationRunId",
                    "_id",
                    "id",
                )
                or self._first(
                    response if isinstance(response, dict) else {},
                    "runId",
                    "publicationRunId",
                    "_id",
                    "id",
                )
            ),
            "status": self._clean(
                self._first(payload, "status", "state")
                or self._first(
                    response if isinstance(response, dict) else {},
                    "status",
                    "state",
                )
                or "QUEUED"
            ),
            "jobs_count": self._as_int(
                self._first(
                    payload,
                    "jobsCount",
                    "jobsCreated",
                    "totalJobs",
                    "total",
                )
                or self._first(
                    response if isinstance(response, dict) else {},
                    "jobsCount",
                    "jobsCreated",
                    "totalJobs",
                    "total",
                ),
                0,
            ),
            "message": self._clean(
                self._first(payload, "message", "detail", "description")
                or self._first(
                    response if isinstance(response, dict) else {},
                    "message",
                    "detail",
                    "description",
                )
            ),
            "folder_id": folder_id,
            "marketplaces": normalized_marketplaces,
            "triggered_at": fields.Datetime.to_string(fields.Datetime.now()),
        }

    @api.model
    def get_publication_run_jobs(self, run_id, limit=50, offset=0):
        self._check_access()
        run_id = self._clean(run_id)
        if not run_id:
            raise UserError(_("Ingresa el run ID para consultar sus publicaciones."))
        limit = min(max(self._as_int(limit, 50), 1), 100)
        offset = max(self._as_int(offset, 0), 0)
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(
                self._madre_base_url(),
                self.PUBLICATION_RUN_JOBS_PATH.format(
                    run_id=quote(run_id, safe="")
                ),
            ),
            params={"limit": limit, "offset": offset},
            headers=self._madre_headers(),
            timeout=self._timeout(),
        )
        return self._normalize_publication_jobs_response(
            response,
            limit=limit,
            offset=offset,
            run_id=run_id,
        )

    @api.model
    def get_pending_publications(self, limit=50):
        self._check_access()
        limit = min(max(self._as_int(limit, 50), 1), 100)
        response = self.env["lqa.api.client"].request_absolute_json(
            "GET",
            self._join_url(
                self._madre_base_url(),
                self.PENDING_PUBLICATIONS_PATH,
            ),
            params={"limit": limit},
            headers=self._madre_headers(),
            timeout=self._timeout(),
        )
        normalized = self._normalize_publication_jobs_response(
            response,
            limit=limit,
            offset=0,
        )
        return {
            "jobs": normalized["jobs"],
            "total": normalized["pagination"]["total"],
            "limit": limit,
        }

    def _send_products(self, folder_id, products):
        if not products:
            raise UserError(_("No hay productos validos para agregar."))

        batches = 0
        for offset in range(0, len(products), self.BULK_BATCH_SIZE):
            batch = products[offset : offset + self.BULK_BATCH_SIZE]
            self.env["lqa.api.client"].request_absolute_json(
                "POST",
                self._join_url(self._madre_base_url(), self.BULK_PRODUCTS_PATH),
                payload={
                    "marketplaceIds": [folder_id],
                    "products": batch,
                },
                headers=self._madre_headers(),
                timeout=self._timeout(),
            )
            batches += 1
        return {
            "folder_id": folder_id,
            "count": len(products),
            "batches": batches,
        }

    def _parse_import_file(self, filename, content_base64):
        filename = self._clean(filename)
        if not filename:
            raise UserError(_("Selecciona un archivo para importar."))
        try:
            content = base64.b64decode(content_base64 or "", validate=True)
        except (ValueError, TypeError) as error:
            raise UserError(_("El archivo recibido no es valido.")) from error
        if not content:
            raise UserError(_("El archivo esta vacio."))
        if len(content) > self.MAX_UPLOAD_BYTES:
            raise UserError(_("El archivo no puede superar 20 MB."))

        extension = os.path.splitext(filename.lower())[1]
        if extension == ".csv":
            rows = self._read_csv_rows(content)
        elif extension == ".xlsx":
            rows = self._read_xlsx_rows(content)
        else:
            raise UserError(_("Usa un archivo de Excel XLSX."))
        return self._products_from_rows(rows)

    def _read_csv_rows(self, content):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
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
                raise UserError(_("El XLSX no contiene hojas para importar."))
            self._check_xlsx_entry_size(workbook, sheet_path)
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
                reference = cell.get("r", "")
                column = self._xlsx_column_index(reference)
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
        self._check_xlsx_entry_size(workbook, path)
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
            if relationship.get("Id") != relationship_id:
                continue
            target = (relationship.get("Target") or "").lstrip("/")
            if target.startswith("xl/"):
                return target
            return posixpath.normpath(f"xl/{target}")
        return ""

    def _check_xlsx_entry_size(self, workbook, path):
        try:
            size = workbook.getinfo(path).file_size
        except KeyError as error:
            raise UserError(_("El XLSX esta incompleto.")) from error
        if size > self.MAX_XLSX_XML_BYTES:
            raise UserError(_("El contenido interno del XLSX es demasiado grande."))

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

    def _products_from_rows(self, rows):
        rows = [row for row in rows if any(self._clean(value) for value in row)]
        if not rows:
            raise UserError(_("El archivo no contiene datos."))

        headers = [self._normalize_header(value) for value in rows[0]]
        product_index = self._find_header_index(headers, self.PRODUCT_ID_HEADERS)
        sku_index = self._find_header_index(headers, self.SELLER_SKU_HEADERS)
        if product_index < 0 or sku_index < 0:
            raise UserError(
                _("El archivo debe incluir las columnas productId (o MLA) y sellerSku (o SKU).")
            )

        products = []
        for row_number, row in enumerate(rows[1:], start=2):
            product_id = self._cell(row, product_index)
            seller_sku = self._cell(row, sku_index)
            if not product_id and not seller_sku:
                continue
            if not product_id or not seller_sku:
                raise UserError(
                    _("Fila %s incompleta: productId y sellerSku son obligatorios.")
                    % row_number
                )
            products.append({"productId": product_id, "sellerSku": seller_sku})
            if len(products) > self.MAX_IMPORT_ROWS:
                raise UserError(
                    _("El archivo supera el limite de %s productos.")
                    % self.MAX_IMPORT_ROWS
                )
        return self._normalize_products(products)

    def _normalize_products(self, products):
        if not isinstance(products, list):
            raise UserError(_("El listado de productos no es valido."))
        normalized = []
        seen = set()
        for item in products:
            item = item if isinstance(item, dict) else {}
            product_id = self._clean(
                item.get("productId") or item.get("product_id") or item.get("mla")
            )
            seller_sku = self._clean(
                item.get("sellerSku") or item.get("seller_sku") or item.get("sku")
            )
            if not product_id or not seller_sku:
                raise UserError(_("Cada producto requiere productId y sellerSku."))
            key = (product_id.lower(), seller_sku.lower())
            if key in seen:
                continue
            seen.add(key)
            normalized.append({"productId": product_id, "sellerSku": seller_sku})
        if len(normalized) > self.MAX_IMPORT_ROWS:
            raise UserError(
                _("No se pueden agregar mas de %s productos por importacion.")
                % self.MAX_IMPORT_ROWS
            )
        return normalized

    def _normalize_folder(self, folder):
        folder = folder if isinstance(folder, dict) else {}
        products = self._extract_list(
            folder,
            ("products", "items", "favorites", "marketplaceFavorites"),
        )
        normalized_products = [
            {
                "productId": self._clean(
                    product.get("productId")
                    or product.get("product_id")
                    or product.get("mla")
                    or product.get("id")
                ),
                "sellerSku": self._clean(
                    product.get("sellerSku")
                    or product.get("seller_sku")
                    or product.get("sku")
                ),
            }
            for product in products
            if isinstance(product, dict)
        ]
        folder_id = (
            folder.get("folderId")
            or folder.get("marketplaceId")
            or folder.get("_id")
            or folder.get("id")
        )
        return {
            "id": folder_id or "",
            "name": self._clean(
                folder.get("name")
                or folder.get("title")
                or folder.get("marketplaceName")
            )
            or "Carpeta sin nombre",
            "product_count": self._as_int(
                folder.get("productCount")
                or folder.get("productsCount")
                or folder.get("count"),
                len(normalized_products),
            ),
            "products": normalized_products,
            "created_at": self._clean(
                folder.get("createdAt") or folder.get("created_at")
            ),
            "updated_at": self._clean(
                folder.get("updatedAt") or folder.get("updated_at")
            ),
        }

    def _normalize_favorite(self, item):
        item = item if isinstance(item, dict) else {}
        product = item.get("product") if isinstance(item.get("product"), dict) else item
        delete_id = self._first(
            product,
            "_id",
            "id",
            "productInternalId",
            "internalId",
            "product_id",
            "productId",
        ) or self._first(
            item,
            "productInternalId",
            "internalId",
            "product_id",
            "productId",
            "_id",
            "id",
        )
        delete_id = self._clean(delete_id)
        if delete_id.upper().startswith("MLA"):
            delete_id = ""
        product_id = self._first(
            product,
            "item_id",
            "itemId",
            "mla",
            "externalId",
            "marketplaceId",
        )
        if not product_id:
            candidate = self._clean(self._first(item, "mla", "externalId", "productId"))
            if candidate.upper().startswith("MLA"):
                product_id = candidate

        return {
            "delete_id": delete_id,
            "product_id": self._clean(product_id),
            "seller_sku": self._clean(
                self._first(
                    product,
                    "sellerSku",
                    "seller_sku",
                    "sku",
                )
                or self._first(item, "sellerSku", "seller_sku", "sku")
            ),
            "title": self._clean(
                self._first(product, "title", "name", "productName")
                or self._first(item, "title", "name")
            )
            or "Producto sin titulo",
            "image": self._clean(
                self._first(
                    product,
                    "thumbnail",
                    "image",
                    "imageUrl",
                    "picture",
                    "pictureUrl",
                )
            ),
            "brand": self._clean(self._first(product, "brand")),
            "category_id": self._clean(
                self._first(product, "categoryId", "category_id")
            ),
            "price": self._as_float(
                self._first(product, "price", "salePrice", "amount"),
                None,
            ),
            "stock": self._as_int(
                self._first(
                    product,
                    "stock",
                    "availableQuantity",
                    "available_quantity",
                    "stockQuantity",
                ),
                0,
            ),
            "visits": self._as_int(
                self._first(product, "visits", "totalVisits", "total_visits"),
                0,
            ),
            "orders": self._as_int(
                self._first(product, "orders", "ordersCount", "orders_count"),
                0,
            ),
        }

    def _normalize_publication_jobs_response(
        self,
        response,
        limit,
        offset=0,
        run_id="",
    ):
        items = self._extract_list(
            response,
            ("jobs", "publicationJobs", "items", "data", "results"),
        )
        response_dict = response if isinstance(response, dict) else {}
        pagination = self._extract_pagination(response)
        total = self._as_int(
            pagination.get("total")
            or pagination.get("totalItems")
            or response_dict.get("total")
            or response_dict.get("count"),
            len(items),
        )
        has_next_value = (
            pagination.get("hasNext")
            if pagination.get("hasNext") is not None
            else response_dict.get("hasNext")
        )
        has_next = (
            bool(has_next_value)
            if has_next_value is not None
            else offset + len(items) < total
        )
        return {
            "run_id": run_id,
            "jobs": [
                self._normalize_publication_job(item, run_id=run_id)
                for item in items
            ],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
                "count": len(items),
                "has_previous": offset > 0,
                "has_next": has_next,
                "next_offset": offset + limit,
                "page": (offset // limit) + 1,
            },
        }

    def _normalize_publication_job(self, item, run_id=""):
        item = item if isinstance(item, dict) else {}
        payload = (
            item.get("job")
            if isinstance(item.get("job"), dict)
            else item
        )
        return {
            "id": self._clean(
                self._first(payload, "_id", "id", "jobId")
            ),
            "run_id": self._clean(
                self._first(
                    payload,
                    "runId",
                    "publicationRunId",
                    "publication_run_id",
                )
                or run_id
            ),
            "sku": self._clean(
                self._first(payload, "sku", "sellerSku", "seller_sku")
            ),
            "marketplace": self._clean(
                self._first(payload, "marketplace", "marketplaceId")
            ).lower(),
            "status": self._clean(
                self._first(payload, "status", "state")
            )
            or "PENDING",
            "attempts": self._as_int(
                self._first(payload, "attempts", "attemptCount", "retries"),
                0,
            ),
            "error_message": self._clean(
                self._first(
                    payload,
                    "error_message",
                    "errorMessage",
                    "error",
                    "lastError",
                )
            ),
            "marketplace_item_id": self._clean(
                self._first(
                    payload,
                    "marketplace_item_id",
                    "marketplaceItemId",
                    "itemId",
                    "externalId",
                )
            ),
            "created_at": self._clean(
                self._first(payload, "createdAt", "created_at")
            ),
            "updated_at": self._clean(
                self._first(
                    payload,
                    "updatedAt",
                    "updated_at",
                    "finishedAt",
                    "finished_at",
                )
            ),
        }

    def _prepare_product_filters(self, filters):
        params = {
            "page": max(self._as_int(filters.get("page"), 1), 1),
            "limit": min(max(self._as_int(filters.get("limit"), 20), 1), 100),
        }
        for key in self.PRODUCT_FILTERS:
            value = self._clean(filters.get(key))
            if value:
                params[key] = value
        if params.get("sortOrder") not in (None, "asc", "desc"):
            params["sortOrder"] = "asc"
        return params

    def _extract_pagination(self, response):
        if not isinstance(response, dict):
            return {}
        pagination = response.get("pagination")
        if isinstance(pagination, dict):
            return pagination
        data = response.get("data")
        if isinstance(data, dict) and isinstance(data.get("pagination"), dict):
            return data["pagination"]
        return {}

    def _build_template_xlsx(self):
        worksheet = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            '<row r="1">'
            f'<c r="A1" t="inlineStr"><is><t>{escape("productId")}</t></is></c>'
            f'<c r="B1" t="inlineStr"><is><t>{escape("sellerSku")}</t></is></c>'
            "</row>"
            '<row r="2">'
            f'<c r="A2" t="inlineStr"><is><t>{escape("MLA123456789")}</t></is></c>'
            f'<c r="B2" t="inlineStr"><is><t>{escape("SKU-001")}</t></is></c>'
            "</row>"
            "</sheetData>"
            "</worksheet>"
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as workbook:
            workbook.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                "</Types>",
            )
            workbook.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                "</Relationships>",
            )
            workbook.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Productos" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>",
            )
            workbook.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                "</Relationships>",
            )
            workbook.writestr("xl/worksheets/sheet1.xml", worksheet)
        return output.getvalue()

    def _madre_headers(self):
        params = self.env["ir.config_parameter"].sudo()
        token = (
            params.get_param("lqa_admin_panel.retailers_madre_api_token", "")
            or os.environ.get("LQA_RETAILERS_MADRE_API_TOKEN", "")
            or params.get_param("lqa_admin_panel.api_token", "")
            or os.environ.get("LQA_API_TOKEN", "")
        ).strip()
        if not token:
            raise UserError(_("Configura el token de Madre para usar el Publicador."))
        return {"Authorization": f"Bearer {token}"}

    def _madre_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param("lqa_admin_panel.retailers_madre_api_url", "")
            or os.environ.get("NEXT_PUBLIC_MADRE_API_URL")
            or "https://api.madre.loquieroaca.com"
        ).strip()

    def _products_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param("lqa_admin_panel.retailers_products_api_url", "")
            or os.environ.get("NEXT_PUBLIC_PRODUCTS_API_URL")
            or "https://api.products.loquieroaca.com"
        ).strip()

    def _timeout(self):
        params = self.env["ir.config_parameter"].sudo()
        return max(
            self._as_int(
                params.get_param("lqa_admin_panel.retailers_timeout_seconds", 60),
                60,
            ),
            1,
        )

    def _check_access(self):
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_commercial_user"):
            raise UserError(_("No tenes permisos para usar el publicador de retailers."))

    def _normalize_folder_id(self, folder_id):
        value = self._clean(folder_id)
        if not value:
            raise UserError(_("Selecciona una carpeta."))
        return int(value) if value.isdigit() else value

    def _favorites_url(self, folder_id):
        return self._join_url(
            self._madre_base_url(),
            self.FAVORITES_PATH.format(folder_id=folder_id),
        )

    @classmethod
    def _extract_list(cls, payload, keys):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = cls._extract_list(value, keys)
                if nested:
                    return nested
        return []

    @staticmethod
    def _extract_record(payload, keys):
        if not isinstance(payload, dict):
            return {}
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload

    @staticmethod
    def _normalize_header(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())

    @staticmethod
    def _find_header_index(headers, candidates):
        for index, header in enumerate(headers):
            if header in candidates:
                return index
        return -1

    @staticmethod
    def _first(source, *keys):
        source = source if isinstance(source, dict) else {}
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return value
        return ""

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
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

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
