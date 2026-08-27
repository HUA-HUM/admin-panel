import base64
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
import json
import posixpath
import re
import threading
import time
import zipfile
from xml.etree import ElementTree

import requests

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.modules.registry import Registry


class SelectionLimitError(UserError):
    """A selection cannot continue without changing its requested scope."""


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
        "listingTypeId",
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
        ("listing_type_id", "tipo_publicacion", "listing_type_id"),
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
        "listing_type_id",
        "price",
        "available_quantity",
        "category_id",
        "permalink",
    )
    MAX_FILTER_SELECTION_ROWS = 500000
    FILTER_SELECTION_PAGE_SIZE = 1000
    FILTER_SELECTION_FETCH_CONCURRENCY = 4
    FILTER_SELECTION_CYCLE_SECONDS = 55
    FILTER_SELECTION_PAGE_RETRIES = 3
    FILTER_SELECTION_MAX_CYCLE_RETRIES = 10
    FILTER_SELECTION_API_TIMEOUT = 90
    CATALOG_QUERY_TIMEOUT = 180
    CATALOG_QUERY_RETRIES = 2
    CATALOG_QUERY_CACHE_MINUTES = 5
    MLA_FILE_MAX_BYTES = 20 * 1024 * 1024
    MLA_FILE_ENRICH_BATCH_SIZE = 100
    MLA_FILE_FETCH_CONCURRENCY = 16
    MLA_FILE_INLINE_CYCLES = 5
    MLA_FILE_API_TIMEOUT = 25
    MLA_FILE_PAGE_RETRIES = 2

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
            timeout=self.CATALOG_QUERY_TIMEOUT,
        )
        products = response.get("products") or []

        return {
            "pagination": response.get("pagination") or {},
            "sort": response.get("sort") or {},
            "products": [self._normalize_product(product) for product in products],
        }

    @api.model
    def start_products_query(self, filters=None):
        self._check_access()
        prepared_filters = dict(filters or {})
        filters_json = json.dumps(
            prepared_filters,
            ensure_ascii=False,
            sort_keys=True,
        )
        cached_query = (
            self.env["lqa.mercadolibre.catalog.query"]
            .sudo()
            .search(
                [
                    ("requested_by_id", "=", self.env.user.id),
                    ("state", "=", "done"),
                    ("filters_json", "=", filters_json),
                    (
                        "finished_at",
                        ">=",
                        fields.Datetime.now()
                        - timedelta(minutes=self.CATALOG_QUERY_CACHE_MINUTES),
                    ),
                ],
                order="id desc",
                limit=1,
            )
        )
        if cached_query:
            return {
                "id": cached_query.id,
                "state": cached_query.state,
                "cached": True,
            }
        query = self.env["lqa.mercadolibre.catalog.query"].sudo().create(
            {
                "requested_by_id": self.env.user.id,
                "filters_json": filters_json,
            }
        )
        thread = threading.Thread(
            target=self._run_products_query,
            args=(self.env.cr.dbname, query.id),
            name=f"lqa-meli-catalog-query-{query.id}",
            daemon=True,
        )
        self.env.cr.postcommit.add(thread.start)
        return {"id": query.id, "state": query.state}

    @api.model
    def get_products_query(self, query_id):
        self._check_access()
        query = (
            self.env["lqa.mercadolibre.catalog.query"]
            .sudo()
            .browse(self._as_int(query_id, 0))
            .exists()
        )
        if not query:
            raise UserError(_("La consulta del catalogo no existe."))
        if (
            not self.env.user.has_group("lqa_admin_panel.group_lqa_admin")
            and query.requested_by_id != self.env.user
        ):
            raise AccessError(_("No tenes acceso a esta consulta."))
        result = {}
        if query.state == "done" and query.result_json:
            try:
                result = json.loads(query.result_json)
            except ValueError:
                result = {}
        return {
            "id": query.id,
            "state": query.state,
            "result": result,
            "error": query.error_message or "",
        }

    @staticmethod
    def _run_products_query(dbname, query_id):
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            query = env["lqa.mercadolibre.catalog.query"].browse(query_id).exists()
            if not query:
                return
            query.write(
                {"state": "running", "started_at": fields.Datetime.now()}
            )
            cr.commit()
            try:
                filters = json.loads(query.filters_json or "{}")
                service = env["lqa.mercadolibre.catalog.service"]
                params = service._prepare_params(filters)
                response = service._request_catalog_query(
                    service._catalog_endpoint(),
                    params,
                )
                products = response.get("products") or []
                result = {
                    "pagination": response.get("pagination") or {},
                    "sort": response.get("sort") or {},
                    "products": [
                        service._normalize_product(product)
                        for product in products
                    ],
                }
                query.write(
                    {
                        "state": "done",
                        "result_json": json.dumps(result, ensure_ascii=False),
                        "error_message": False,
                        "finished_at": fields.Datetime.now(),
                    }
                )
            except Exception as error:
                query.write(
                    {
                        "state": "failed",
                        "error_message": str(error),
                        "finished_at": fields.Datetime.now(),
                    }
                )
            cr.commit()

    def _request_catalog_query(self, endpoint, params):
        last_error = None
        for attempt in range(1, self.CATALOG_QUERY_RETRIES + 1):
            try:
                response = requests.get(
                    endpoint,
                    headers={"Accept": "application/json"},
                    params=params,
                    timeout=self.CATALOG_QUERY_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt < self.CATALOG_QUERY_RETRIES:
                    time.sleep(attempt * 3)
        raise UserError(
            _("Catalog Sync API no respondio luego de %s intentos: %s")
            % (self.CATALOG_QUERY_RETRIES, last_error)
        )

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
    def import_mla_file_to_folder(self, name, filename, content_base64):
        self._check_access()
        name = self._clean(name)
        filename = self._clean(filename)
        if not name:
            raise UserError(_("Indica un nombre para la carpeta."))
        if not filename or not content_base64:
            raise UserError(_("Selecciona un archivo CSV o XLSX."))
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in {"csv", "xlsx"}:
            raise UserError(_("El archivo debe ser CSV o XLSX."))
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (ValueError, TypeError) as error:
            raise UserError(_("No se pudo leer el archivo enviado.")) from error
        if not content:
            raise UserError(_("El archivo esta vacio."))
        if len(content) > self.MLA_FILE_MAX_BYTES:
            raise UserError(_("El archivo puede pesar como maximo 20 MB."))

        rows = (
            self._read_mla_csv_rows(content)
            if extension == "csv"
            else self._read_mla_xlsx_rows(content)
        )
        mla_codes, invalid_count = self._extract_mla_codes(rows)
        if not mla_codes:
            raise UserError(_("No encontre MLAs validos en la primera columna."))
        if len(mla_codes) > self.MAX_FILTER_SELECTION_ROWS:
            raise UserError(
                _("El archivo supera el maximo de %s MLAs por carpeta.")
                % self.MAX_FILTER_SELECTION_ROWS
            )

        folder = self.env["lqa.mercadolibre.selection.folder"].create(
            {
                "name": name,
                "description": _("Importada desde %s") % filename,
            }
        )
        job = self.env["lqa.mercadolibre.selection.job"].sudo().create(
            {
                "folder_id": folder.id,
                "requested_by_id": self.env.user.id,
                "source_type": "mla_file",
                "input_filename": filename,
                "mla_codes_json": json.dumps(mla_codes, ensure_ascii=False),
                "filters_json": "{}",
                "matched_count": len(mla_codes),
                "invalid_count": invalid_count,
                "initial_count_recorded": True,
            }
        )
        thread = threading.Thread(
            target=self._run_filtered_selection_job,
            args=(self.env.cr.dbname, job.id),
            name=f"lqa-meli-mla-import-{job.id}",
            daemon=True,
        )
        self.env.cr.postcommit.add(thread.start)
        return {
            "folder": self._folder_to_dict(folder),
            "job": self._selection_job_to_dict(job),
        }

    @api.model
    def save_products_to_folder(self, folder_id, products):
        self._check_access()
        folder = self._get_folder(folder_id)
        if not isinstance(products, list) or not products:
            raise UserError(_("Selecciona al menos un producto."))

        current_count = self.env["lqa.mercadolibre.selection.item"].search_count(
            [("folder_id", "=", folder.id)]
        )
        result = self._save_product_batch(
            folder,
            products,
            max_folder_size=self.MAX_FILTER_SELECTION_ROWS,
            current_count=current_count,
        )
        return {
            "folder": self._folder_to_dict(folder),
            **result,
        }

    @api.model
    def save_filtered_products_to_folder(self, folder_id, filters=None):
        self._check_access()
        folder = self._get_folder(folder_id)
        active_job = (
            self.env["lqa.mercadolibre.selection.job"]
            .sudo()
            .search_count(
                [
                    ("folder_id", "=", folder.id),
                    ("state", "in", ["queued", "running"]),
                ]
            )
        )
        if active_job:
            raise UserError(
                _("Esta carpeta ya tiene un guardado masivo en curso.")
            )
        filters = dict(filters or {})
        filters["offset"] = 0
        filters["limit"] = self.FILTER_SELECTION_PAGE_SIZE
        initial_folder_count = self.env[
            "lqa.mercadolibre.selection.item"
        ].search_count([("folder_id", "=", folder.id)])
        job = self.env["lqa.mercadolibre.selection.job"].sudo().create(
            {
                "folder_id": folder.id,
                "requested_by_id": self.env.user.id,
                "filters_json": json.dumps(filters, ensure_ascii=False),
                "initial_folder_count": initial_folder_count,
                "initial_count_recorded": True,
            }
        )
        thread = threading.Thread(
            target=self._run_filtered_selection_job,
            args=(self.env.cr.dbname, job.id),
            name=f"lqa-meli-selection-{job.id}",
            daemon=True,
        )
        self.env.cr.postcommit.add(thread.start)
        return self._selection_job_to_dict(job)

    @api.model
    def get_selection_job(self, job_id):
        self._check_access()
        job = (
            self.env["lqa.mercadolibre.selection.job"]
            .sudo()
            .browse(self._as_int(job_id, 0))
            .exists()
        )
        if not job:
            raise UserError(_("El proceso de guardado no existe."))
        if (
            not self.env.user.has_group("lqa_admin_panel.group_lqa_admin")
            and job.requested_by_id != self.env.user
        ):
            raise AccessError(_("No tenes acceso a este proceso."))
        self._resume_stale_mla_file_job(job)
        return self._selection_job_to_dict(job)

    @api.model
    def get_active_selection_job(self):
        self._check_access()
        job = (
            self.env["lqa.mercadolibre.selection.job"]
            .sudo()
            .search(
                [
                    ("requested_by_id", "=", self.env.user.id),
                    ("state", "in", ["queued", "running"]),
                ],
                order="id desc",
                limit=1,
            )
        )
        if not job:
            job = (
                self.env["lqa.mercadolibre.selection.job"]
                .sudo()
                .search(
                    [
                        ("requested_by_id", "=", self.env.user.id),
                        ("state", "=", "failed"),
                    ],
                    order="id desc",
                    limit=1,
                )
            )
        return self._selection_job_to_dict(job) if job else False

    @api.model
    def get_latest_mla_file_job(self):
        self._check_access()
        job = (
            self.env["lqa.mercadolibre.selection.job"]
            .sudo()
            .search(
                [
                    ("requested_by_id", "=", self.env.user.id),
                    ("source_type", "=", "mla_file"),
                ],
                order="id desc",
                limit=1,
            )
        )
        if job:
            self._resume_stale_mla_file_job(job)
        return self._selection_job_to_dict(job) if job else False

    def _resume_stale_mla_file_job(self, job):
        """Restart an abandoned import while its owner is watching the UI."""
        if job.source_type != "mla_file":
            return
        now = fields.Datetime.now()
        queued_before = now - timedelta(minutes=1)
        running_before = now - timedelta(minutes=10)
        should_resume = (
            job.state == "queued"
            and (
                not job.last_progress_at
                or job.last_progress_at < queued_before
            )
        ) or (
            job.state == "running"
            and (
                not job.last_progress_at
                or job.last_progress_at < running_before
            )
        )
        if not should_resume:
            return
        job.write(
            {
                "state": "running",
                "started_at": job.started_at or now,
                "last_progress_at": now,
            }
        )
        thread = threading.Thread(
            target=self._run_filtered_selection_job,
            args=(self.env.cr.dbname, job.id),
            name=f"lqa-meli-mla-resume-{job.id}",
            daemon=True,
        )
        self.env.cr.postcommit.add(thread.start)

    @api.model
    def retry_selection_job(self, job_id):
        self._check_access()
        job = (
            self.env["lqa.mercadolibre.selection.job"]
            .sudo()
            .browse(self._as_int(job_id, 0))
            .exists()
        )
        if not job:
            raise UserError(_("El proceso de guardado no existe."))
        if (
            not self.env.user.has_group("lqa_admin_panel.group_lqa_admin")
            and job.requested_by_id != self.env.user
        ):
            raise AccessError(_("No tenes acceso a este proceso."))
        if job.state != "failed":
            raise UserError(_("Solo se pueden reintentar procesos fallidos."))
        job.write(
            {
                "state": "queued",
                "retry_count": 0,
                "error_message": False,
                "finished_at": False,
            }
        )
        thread = threading.Thread(
            target=self._run_filtered_selection_job,
            args=(self.env.cr.dbname, job.id),
            name=f"lqa-meli-selection-retry-{job.id}",
            daemon=True,
        )
        self.env.cr.postcommit.add(thread.start)
        return self._selection_job_to_dict(job)

    @staticmethod
    def _run_filtered_selection_job(dbname, job_id):
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            job = env["lqa.mercadolibre.selection.job"].browse(job_id).exists()
            if not job:
                return
            service = env["lqa.mercadolibre.catalog.service"]
            max_cycles = (
                service.MLA_FILE_INLINE_CYCLES
                if job.source_type == "mla_file"
                else 1
            )
            for _cycle in range(max_cycles):
                service._process_selection_job_cycle(job)
                cr.commit()
                job.invalidate_recordset()
                if job.state != "queued":
                    break

    @api.model
    def process_pending_selection_jobs(self):
        """Continue one queued job per cron tick and recover abandoned workers."""
        stale_before = fields.Datetime.now() - timedelta(minutes=5)
        job_model = self.env["lqa.mercadolibre.selection.job"].sudo()
        stale_jobs = job_model.search(
            [
                ("state", "=", "running"),
                "|",
                ("last_progress_at", "=", False),
                ("last_progress_at", "<", stale_before),
            ]
        )
        if stale_jobs:
            stale_jobs.write({"state": "queued"})
        job = job_model.search([("state", "=", "queued")], order="id", limit=1)
        if job:
            self._process_selection_job_cycle(job)
        return True

    def _process_selection_job_cycle(self, job):
        now = fields.Datetime.now()
        job.write(
            {
                "state": "running",
                "started_at": job.started_at or now,
                "last_progress_at": now,
            }
        )
        self.env.cr.commit()
        try:
            if job.source_type == "mla_file":
                result = self._save_mla_file_products_in_batches(job)
            else:
                filters = json.loads(job.filters_json or "{}")
                result = self._save_filtered_products_in_batches(job, filters)
            if result.pop("completed", False):
                job.write(
                    {
                        "state": "done",
                        "finished_at": fields.Datetime.now(),
                        "error_message": False,
                        **result,
                    }
                )
            else:
                job.write({"state": "queued", **result})
        except SelectionLimitError as error:
            job.write(
                {
                    "state": "failed",
                    "finished_at": fields.Datetime.now(),
                    "error_message": str(error),
                }
            )
        except Exception as error:
            retry_count = job.retry_count + 1
            values = {
                "retry_count": retry_count,
                "error_message": str(error),
                "last_progress_at": fields.Datetime.now(),
            }
            if retry_count >= self.FILTER_SELECTION_MAX_CYCLE_RETRIES:
                values.update(
                    {"state": "failed", "finished_at": fields.Datetime.now()}
                )
            else:
                values["state"] = "queued"
            job.write(values)
        self.env.cr.commit()

    def _save_mla_file_products_in_batches(self, job):
        mla_codes = json.loads(job.mla_codes_json or "[]")
        cursor = job.cursor_offset or job.processed_count or 0
        endpoint = self._catalog_endpoint()
        cycle_started = time.monotonic()
        added = job.added_count
        updated = job.updated_count
        not_found_total = job.not_found_count
        existing_count = self.env[
            "lqa.mercadolibre.selection.item"
        ].search_count([("folder_id", "=", job.folder_id.id)])
        if cursor >= len(mla_codes):
            return {
                "completed": True,
                "matched_count": len(mla_codes),
                "processed_count": cursor,
                "cursor_offset": cursor,
                "added_count": added,
                "updated_count": updated,
                "not_found_count": not_found_total,
            }

        while cursor < len(mla_codes):
            codes = mla_codes[cursor : cursor + self.MLA_FILE_ENRICH_BATCH_SIZE]
            params_list = [
                self._prepare_params(
                    {"search": code, "limit": 20, "offset": 0},
                    max_limit=20,
                )
                for code in codes
            ]
            with ThreadPoolExecutor(
                max_workers=min(self.MLA_FILE_FETCH_CONCURRENCY, len(codes))
            ) as executor:
                responses = list(
                    executor.map(
                        lambda params: self._request_mla_file_page(
                            endpoint, params
                        ),
                        params_list,
                    )
                )

            products = []
            not_found = 0
            for code, response in zip(codes, responses):
                exact_product = next(
                    (
                        product
                        for product in (response.get("products") or [])
                        if self._normalize_mla(
                            self._first(product, "item_id", "itemId")
                        )
                        == code
                    ),
                    None,
                )
                if exact_product:
                    products.append(self._normalize_product(exact_product))
                elif response.get("_lookup_error"):
                    products.append(
                        {
                            "item_id": code,
                            "title": _(
                                "No se pudo consultar esta MLA en Catalog API"
                            ),
                            "status": "lookup_error",
                        }
                    )
                else:
                    not_found += 1
                    products.append(
                        {
                            "item_id": code,
                            "title": _("MLA no encontrado en Catalog API"),
                            "status": "not_found",
                        }
                    )

            batch_result = self._save_product_batch(
                job.folder_id,
                products,
                max_folder_size=self.MAX_FILTER_SELECTION_ROWS,
                current_count=existing_count,
                update_existing=True,
            )
            added += batch_result["added"]
            updated += batch_result["updated"]
            not_found_total += not_found
            existing_count += batch_result["added"]
            cursor += len(codes)
            progress = {
                "matched_count": len(mla_codes),
                "processed_count": cursor,
                "cursor_offset": cursor,
                "added_count": added,
                "updated_count": updated,
                "not_found_count": not_found_total,
                "last_progress_at": fields.Datetime.now(),
            }
            job.write(progress)
            self.env.cr.commit()
            if time.monotonic() - cycle_started >= self.FILTER_SELECTION_CYCLE_SECONDS:
                return {"completed": False, **progress}

        return {"completed": True, **progress}

    def _request_mla_file_page(self, endpoint, params):
        try:
            return self._request_selection_page_http(
                endpoint,
                params,
                self.MLA_FILE_API_TIMEOUT,
                self.MLA_FILE_PAGE_RETRIES,
            )
        except Exception as error:
            return {"products": [], "_lookup_error": str(error)}

    def _save_filtered_products_in_batches(self, job, filters):
        endpoint = self._catalog_endpoint()
        filters = dict(filters or {})
        cursor_offset = job.cursor_offset or job.processed_count or 0
        filters["offset"] = cursor_offset
        filters["limit"] = self.FILTER_SELECTION_PAGE_SIZE
        processed = job.processed_count or 0
        added = job.added_count or 0
        updated = job.updated_count or 0
        matched = job.matched_count or 0
        cycle_started = time.monotonic()
        existing_count = self.env["lqa.mercadolibre.selection.item"].search_count(
            [("folder_id", "=", job.folder_id.id)]
        )
        parallel_safe = False

        while True:
            page_offsets = [cursor_offset]
            if parallel_safe and matched:
                remaining = max(matched - cursor_offset, 0)
                page_count = min(
                    self.FILTER_SELECTION_FETCH_CONCURRENCY,
                    max(
                        1,
                        (remaining + self.FILTER_SELECTION_PAGE_SIZE - 1)
                        // self.FILTER_SELECTION_PAGE_SIZE,
                    ),
                )
                page_offsets = [
                    cursor_offset + index * self.FILTER_SELECTION_PAGE_SIZE
                    for index in range(page_count)
                ]
            params_list = []
            for page_offset in page_offsets:
                page_filters = dict(filters, offset=page_offset)
                params_list.append(
                    self._prepare_params(
                        page_filters,
                        max_limit=self.FILTER_SELECTION_PAGE_SIZE,
                    )
                )
            responses = self._request_selection_pages(
                endpoint,
                params_list,
            )

            for page_offset, response in zip(page_offsets, responses):
                if page_offset != cursor_offset:
                    break
                pagination = response.get("pagination") or {}
                matched = self._as_int(pagination.get("total"), matched)
                if matched > self.MAX_FILTER_SELECTION_ROWS:
                    raise SelectionLimitError(
                        _(
                            "El filtro devuelve %s productos y el maximo por carpeta es %s. Refiná el filtro antes de guardar."
                        )
                        % (matched, self.MAX_FILTER_SELECTION_ROWS)
                    )
                if processed == 0 and (
                    existing_count + matched > self.MAX_FILTER_SELECTION_ROWS
                ):
                    raise SelectionLimitError(
                        _(
                            "La carpeta ya contiene %s productos. Este filtro podria superar el maximo de %s productos por carpeta."
                        )
                        % (existing_count, self.MAX_FILTER_SELECTION_ROWS)
                    )

                products = [
                    self._normalize_product(product)
                    for product in (response.get("products") or [])
                ]
                if not products:
                    return {
                        "completed": True,
                        "matched_count": matched or processed,
                        "processed_count": processed,
                        "cursor_offset": cursor_offset,
                        "added_count": added,
                        "updated_count": updated,
                    }

                batch_result = self._save_product_batch(
                    job.folder_id,
                    products,
                    max_folder_size=self.MAX_FILTER_SELECTION_ROWS,
                    current_count=existing_count,
                    update_existing=False,
                )
                added += batch_result["added"]
                updated += batch_result["updated"]
                existing_count += batch_result["added"]
                processed += len(products)
                cursor_offset += len(products)
                job.write(
                    {
                        "matched_count": matched,
                        "processed_count": processed,
                        "cursor_offset": cursor_offset,
                        "added_count": added,
                        "updated_count": updated,
                        "last_progress_at": fields.Datetime.now(),
                        "error_message": False,
                    }
                )
                self.env.cr.commit()

                if matched and processed >= matched:
                    return {
                        "completed": True,
                        "matched_count": matched,
                        "processed_count": processed,
                        "cursor_offset": cursor_offset,
                        "added_count": added,
                        "updated_count": updated,
                    }
                expected_page_size = min(
                    self.FILTER_SELECTION_PAGE_SIZE,
                    max(matched - page_offset, 0),
                )
                if len(products) < expected_page_size:
                    parallel_safe = False
                    break
                parallel_safe = len(products) == self.FILTER_SELECTION_PAGE_SIZE

            filters["offset"] = cursor_offset
            if time.monotonic() - cycle_started >= self.FILTER_SELECTION_CYCLE_SECONDS:
                return {
                    "completed": False,
                    "matched_count": matched,
                    "processed_count": processed,
                    "cursor_offset": cursor_offset,
                    "added_count": added,
                    "updated_count": updated,
                }

    def _request_selection_pages(self, endpoint, params_list):
        if len(params_list) == 1:
            return [self._request_selection_page(endpoint, params_list[0])]
        try:
            with ThreadPoolExecutor(max_workers=len(params_list)) as executor:
                return list(
                    executor.map(
                        lambda params: self._request_selection_page_http(
                            endpoint,
                            params,
                            self.FILTER_SELECTION_API_TIMEOUT,
                            self.FILTER_SELECTION_PAGE_RETRIES,
                        ),
                        params_list,
                    )
                )
        except Exception as error:
            raise UserError(
                _("No se pudo consultar un lote paralelo del catalogo: %s")
                % error
            ) from error

    @staticmethod
    def _request_selection_page_http(endpoint, params, timeout, retries):
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                response = requests.get(
                    endpoint,
                    headers={"Accept": "application/json"},
                    params=params,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt < retries:
                    time.sleep(attempt * 2)
        raise last_error

    def _request_selection_page(self, endpoint, params):
        last_error = None
        for attempt in range(1, self.FILTER_SELECTION_PAGE_RETRIES + 1):
            try:
                return self.env["lqa.api.client"].request_absolute_json(
                    "GET",
                    endpoint,
                    params=params,
                    timeout=self.FILTER_SELECTION_API_TIMEOUT,
                )
            except UserError as error:
                last_error = error
                if attempt < self.FILTER_SELECTION_PAGE_RETRIES:
                    time.sleep(attempt * 2)
        raise last_error

    def _save_product_batch(
        self,
        folder,
        products,
        max_folder_size=None,
        current_count=None,
        update_existing=True,
    ):
        line_model = self.env["lqa.mercadolibre.selection.item"]
        values_by_key = {}
        for product in products:
            values = self._selection_values_from_product(folder, product)
            values_by_key[values["product_key"]] = values

        existing_by_key = {
            line.product_key: line
            for line in line_model.search(
                [
                    ("folder_id", "=", folder.id),
                    ("product_key", "in", list(values_by_key)),
                ]
            )
        }
        to_create = []
        updated = 0
        for product_key, values in values_by_key.items():
            existing = existing_by_key.get(product_key)
            if existing:
                if update_existing:
                    existing.write(values)
                updated += 1
            else:
                to_create.append(values)
        if max_folder_size is not None:
            folder_count = (
                current_count
                if current_count is not None
                else line_model.search_count([("folder_id", "=", folder.id)])
            )
            if folder_count + len(to_create) > max_folder_size:
                raise UserError(
                    _("Una carpeta puede contener como maximo %s productos.")
                    % max_folder_size
                )
        if to_create:
            line_model.create(to_create)

        return {
            "added": len(to_create),
            "updated": updated,
            "total": len(to_create) + updated,
        }

    def _selection_job_to_dict(self, job):
        folder_count = job.initial_folder_count + job.added_count
        if not job.initial_count_recorded:
            folder_count = self.env[
                "lqa.mercadolibre.selection.item"
            ].sudo().search_count([("folder_id", "=", job.folder_id.id)])
        return {
            "id": job.id,
            "sourceType": job.source_type,
            "filename": job.input_filename or "",
            "folderId": job.folder_id.id,
            "folderName": job.folder_id.name,
            "state": job.state,
            "matched": job.matched_count,
            "processed": job.processed_count,
            "added": job.added_count,
            "updated": job.updated_count,
            "notFound": job.not_found_count,
            "invalid": job.invalid_count,
            "folderCount": folder_count,
            "retries": job.retry_count,
            "error": job.error_message or "",
            "maxProducts": self.MAX_FILTER_SELECTION_ROWS,
        }

    def _extract_mla_codes(self, rows):
        clean_rows = [row for row in rows if any(self._clean(value) for value in row)]
        if not clean_rows:
            return [], 0
        header = [self._clean(value).lower() for value in clean_rows[0]]
        mla_index = next(
            (
                index
                for index, value in enumerate(header)
                if re.sub(r"[^a-z0-9]", "", value) in {
                    "mla",
                    "itemid",
                    "publicacion",
                    "publicationid",
                }
            ),
            -1,
        )
        data_rows = clean_rows[1:] if mla_index >= 0 else clean_rows
        mla_index = mla_index if mla_index >= 0 else 0
        codes = []
        seen = set()
        invalid = 0
        for row in data_rows:
            raw_value = row[mla_index] if mla_index < len(row) else ""
            code = self._normalize_mla(raw_value)
            if not code:
                if self._clean(raw_value):
                    invalid += 1
                continue
            if code in seen:
                continue
            seen.add(code)
            codes.append(code)
        return codes, invalid

    @staticmethod
    def _normalize_mla(value):
        clean_value = re.sub(r"[\s-]+", "", str(value or "").strip()).upper()
        match = re.fullmatch(r"(?:MLA)?(\d{6,})", clean_value)
        return f"MLA{match.group(1)}" if match else ""

    def _read_mla_csv_rows(self, content):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel_tab if "\t" in text[:4096] else csv.excel
        return list(csv.reader(io.StringIO(text), dialect))

    def _read_mla_xlsx_rows(self, content):
        try:
            workbook = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as error:
            raise UserError(_("El archivo XLSX no es valido.")) from error
        with workbook:
            shared_strings = self._mla_xlsx_shared_strings(workbook)
            sheet_path = self._mla_xlsx_first_sheet_path(workbook)
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
                column = self._mla_xlsx_column_index(cell.get("r", ""))
                if column < 0:
                    continue
                values[column] = self._mla_xlsx_cell_value(
                    cell, shared_strings, namespace
                )
                max_column = max(max_column, column)
            if max_column >= 0:
                rows.append([values.get(index, "") for index in range(max_column + 1)])
        return rows

    def _mla_xlsx_shared_strings(self, workbook):
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

    def _mla_xlsx_first_sheet_path(self, workbook):
        namespace = {
            "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "p": "http://schemas.openxmlformats.org/package/2006/relationships",
        }
        try:
            root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(
                workbook.read("xl/_rels/workbook.xml.rels")
            )
        except (KeyError, ElementTree.ParseError):
            return ""
        sheet = root.find("x:sheets/x:sheet", namespace)
        if sheet is None:
            return ""
        relationship_id = sheet.get(f"{{{namespace['r']}}}id")
        for relationship in relationships.findall("p:Relationship", namespace):
            if relationship.get("Id") == relationship_id:
                target = (relationship.get("Target") or "").lstrip("/")
                return target if target.startswith("xl/") else posixpath.normpath(f"xl/{target}")
        return ""

    def _mla_xlsx_cell_value(self, cell, shared_strings, namespace):
        cell_type = cell.get("t", "")
        if cell_type == "inlineStr":
            return "".join(node.text or "" for node in cell.findall(".//x:t", namespace))
        value_node = cell.find("x:v", namespace)
        value = value_node.text if value_node is not None else ""
        if cell_type == "s":
            index = self._as_int(value, -1)
            return shared_strings[index] if 0 <= index < len(shared_strings) else ""
        return value

    @staticmethod
    def _mla_xlsx_column_index(reference):
        letters = re.match(r"[A-Za-z]+", str(reference or ""))
        if not letters:
            return -1
        result = 0
        for letter in letters.group(0).upper():
            result = result * 26 + ord(letter) - ord("A") + 1
        return result - 1

    def _catalog_endpoint(self):
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
        return endpoint

    def _fetch_filtered_products(self, filters):
        filters = dict(filters or {})
        filters["offset"] = 0
        filters["limit"] = 100
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
            pagination = response.get("pagination") or {}
            total = self._as_int(pagination.get("total"), total or 0)
            if total > self.MAX_FILTER_SELECTION_ROWS:
                raise UserError(
                    _(
                        "El filtro devuelve %s productos. Refiná el filtro o baja el total a %s para guardar en carpeta."
                    )
                    % (total, self.MAX_FILTER_SELECTION_ROWS)
                )
            page_products = [
                self._normalize_product(product)
                for product in (response.get("products") or [])
            ]
            for product in page_products:
                key = self._product_key(product)
                if key and key not in seen:
                    seen.add(key)
                    products.append(product)
            if not page_products:
                break
            if len(products) >= total and total:
                break
            offset = self._as_int(params.get("offset"), 0) + self._as_int(
                params.get("limit"), 100
            )
            if offset <= self._as_int(params.get("offset"), 0):
                break
            filters["offset"] = offset
            if len(products) >= self.MAX_FILTER_SELECTION_ROWS:
                break
        return products, total or len(products)

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
                    self._csv_line_value(line, column_map[key])
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
            "listing_type_id": self._clean(
                self._first(product, "listing_type_id", "listingTypeId")
            ),
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

    def _prepare_params(self, filters, max_limit=100):
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

        max_limit = max(self._as_int(max_limit, 100), 1)
        params["limit"] = min(
            max(self._as_int(params.get("limit"), 100), 1),
            max_limit,
        )
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

    def _csv_line_value(self, line, column):
        value = getattr(line, column[2], "")
        if value not in (None, False, ""):
            return self._csv_value(value)
        if column[0] == "listing_type_id" and line.payload_json:
            try:
                payload = json.loads(line.payload_json)
            except ValueError:
                payload = {}
            return self._csv_value(
                self._first(payload, "listing_type_id", "listingTypeId")
            )
        return self._csv_value(value)

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
