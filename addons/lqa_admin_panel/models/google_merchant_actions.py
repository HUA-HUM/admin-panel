import base64
import csv
import io
import json
import os
import posixpath
import re
import zipfile
from urllib.parse import quote
from xml.etree import ElementTree

import requests
import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaGoogleMerchantActionRun(models.Model):
    _name = "lqa.google.merchant.action.run"
    _description = "Ejecucion de acciones de Google Merchant"
    _order = "triggered_at desc, id desc"

    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    action_type = fields.Selection(
        [
            ("publish_all", "Carga masiva de productos"),
            ("delete_all", "Eliminar catalogo completo"),
            ("delete_selected", "Eliminar productos Google Merchant"),
        ],
        string="Accion",
        required=True,
        default="delete_all",
        readonly=True,
    )
    status = fields.Selection(
        [
            ("processing", "Procesando"),
            ("completed", "Completado"),
            ("partial", "Parcial"),
            ("failed", "Fallido"),
        ],
        string="Estado",
        required=True,
        default="processing",
        readonly=True,
        index=True,
    )
    message = fields.Text(string="Mensaje", readonly=True)
    response_json = fields.Text(string="Respuesta API", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)
    requested_count = fields.Integer(string="Solicitados", readonly=True)
    deleted_count = fields.Integer(string="Eliminados", readonly=True)
    failed_count = fields.Integer(string="Con error", readonly=True)
    triggered_at = fields.Datetime(
        string="Ejecutado",
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    finished_at = fields.Datetime(string="Finalizado", readonly=True)
    line_ids = fields.One2many(
        "lqa.google.merchant.action.line",
        "run_id",
        string="Lineas",
        readonly=True,
    )

    def to_panel_dict(self):
        self.ensure_one()
        try:
            response = json.loads(self.response_json or "{}")
        except (TypeError, ValueError):
            response = {}
        line_preview = [
            line.to_panel_dict()
            for line in self.line_ids.sorted(lambda item: (item.sequence, item.id))[:50]
        ]
        return {
            "id": self.id,
            "action_type": self.action_type,
            "status": self.status,
            "message": self.message or "",
            "error_message": self.error_message or "",
            "requested_count": self.requested_count,
            "deleted_count": self.deleted_count,
            "failed_count": self.failed_count,
            "pending_count": len(
                self.line_ids.filtered(lambda line: line.status in ("pending", "processing"))
            ),
            "line_preview": line_preview,
            "response": response,
            "response_json": (
                json.dumps(response, ensure_ascii=False, indent=2, default=str)
                if response
                else ""
            ),
            "triggered_at": fields.Datetime.to_string(self.triggered_at),
            "finished_at": fields.Datetime.to_string(self.finished_at),
            "user_name": self.user_id.name or "",
        }

    @api.model
    def _cron_process_pending_delete_runs(self, run_limit=2, line_limit=50):
        runs = self.search(
            [
                ("action_type", "=", "delete_selected"),
                ("status", "=", "processing"),
                ("line_ids.status", "in", ("pending", "processing")),
            ],
            order="triggered_at asc, id asc",
            limit=run_limit,
        )
        service = self.env["lqa.google.merchant.actions.service"].sudo()
        for run in runs:
            service.process_delete_run(run.id, line_limit=line_limit)


class LqaGoogleMerchantActionLine(models.Model):
    _name = "lqa.google.merchant.action.line"
    _description = "Producto de ejecucion Google Merchant"
    _order = "sequence asc, id asc"

    run_id = fields.Many2one(
        "lqa.google.merchant.action.run",
        string="Ejecucion",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    sku = fields.Char(string="SKU / ID producto", required=True, index=True)
    content_language = fields.Char(string="Idioma", required=True, default="es")
    feed_label = fields.Char(string="Etiqueta feed", required=True, default="AR")
    status = fields.Selection(
        [
            ("pending", "En cola"),
            ("processing", "Procesando"),
            ("completed", "Eliminado"),
            ("failed", "Error"),
        ],
        string="Estado",
        required=True,
        default="pending",
        readonly=True,
        index=True,
    )
    message = fields.Text(string="Mensaje", readonly=True)
    response_json = fields.Text(string="Respuesta API", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)
    started_at = fields.Datetime(string="Inicio", readonly=True)
    finished_at = fields.Datetime(string="Fin", readonly=True)

    def to_panel_dict(self):
        self.ensure_one()
        return {
            "id": self.id,
            "sku": self.sku or "",
            "content_language": self.content_language or "",
            "feed_label": self.feed_label or "",
            "status": self.status or "",
            "message": self.message or "",
            "error_message": self.error_message or "",
        }


class LqaGoogleMerchantActionsService(models.AbstractModel):
    _name = "lqa.google.merchant.actions.service"
    _description = "Servicio de acciones de Google Merchant"

    DEFAULT_PRODUCTS_API_URL = "https://api.products.loquieroaca.com"
    DEFAULT_MADRE_API_URL = "https://api.madre.loquieroaca.com"
    DEFAULT_MARKETPLACE_API_URL = "https://api.marketplace.loquieroaca.com"
    PUBLISH_ALL_PATH = "/api/internal/google-merchant/products/publish-all"
    DELETE_ALL_PATH = "/api/internal/google-merchant/products/delete-all"
    DELETE_ONE_PATH = "/internal/google-merchant/products/{sku}"
    GOOGLE_CATALOG_PATH = "/api/internal/marketplace/products/items/all"
    CONFIRMATION_TEXT = "ELIMINAR TODO"
    DEFAULT_TIMEOUT_SECONDS = 180
    DEFAULT_TRIGGER_TIMEOUT_SECONDS = 8
    MAX_DELETE_ROWS = 10000
    MAX_UPLOAD_BYTES = 20 * 1024 * 1024
    MAX_XLSX_XML_BYTES = 40 * 1024 * 1024
    PRODUCT_ID_HEADERS = {
        "sku",
        "id",
        "productid",
        "idproducto",
        "iddeproducto",
        "idpublicacion",
        "offerid",
        "productinputid",
    }
    FEED_LABEL_HEADERS = {
        "feed",
        "feedlabel",
        "feed_label",
        "etiquetadefeed",
        "labeldefeed",
    }
    CONTENT_LANGUAGE_HEADERS = {
        "language",
        "lang",
        "idioma",
        "contentlanguage",
        "content_language",
    }

    @api.model
    def publish_all_products(self, options=None):
        self._check_access()
        options = options if isinstance(options, dict) else {}
        payload = {
            "limit": min(max(self._as_int(options.get("limit"), 50), 1), 1000),
            "offset": max(self._as_int(options.get("offset"), 0), 0),
        }
        run = self.env["lqa.google.merchant.action.run"].sudo().create(
            {
                "user_id": self.env.user.id,
                "action_type": "publish_all",
                "status": "processing",
                "message": _("Disparando carga masiva en Products API."),
                "response_json": json.dumps(
                    {"request": payload},
                    ensure_ascii=False,
                    default=str,
                ),
            }
        )
        try:
            response = self._trigger_products_job(self.PUBLISH_ALL_PATH, payload)
            response_payload = response if isinstance(response, (dict, list)) else {}
            failed = bool(
                isinstance(response_payload, dict)
                and (
                    response_payload.get("success") is False
                    or self._clean(
                        response_payload.get("status") or response_payload.get("state")
                    ).upper()
                    in {"ERROR", "FAILED", "FAILURE"}
                )
            )
            run.write(
                {
                    "status": "failed" if failed else "processing",
                    "message": ""
                    if failed
                    else _(
                        "Carga masiva enviada. Products API continua procesando en segundo plano."
                    ),
                    "error_message": self._response_message(response_payload)
                    if failed
                    else "",
                    "response_json": json.dumps(
                        {
                            "request": payload,
                            "response": response_payload,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                    "finished_at": fields.Datetime.now() if failed else False,
                }
            )
        except requests.ReadTimeout:
            run.write(
                {
                    "status": "processing",
                    "message": _(
                        "Carga masiva enviada. Products API no respondio enseguida, queda procesando en segundo plano."
                    ),
                    "response_json": json.dumps(
                        {
                            "request": payload,
                            "note": "Read timeout after trigger; treated as background processing.",
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )
        except UserError as error:
            run.write(
                {
                    "status": "failed",
                    "error_message": str(error),
                    "finished_at": fields.Datetime.now(),
                }
            )
        return run.to_panel_dict()

    @api.model
    def delete_all_products(self, confirmation):
        self._check_access()
        if self._clean(confirmation).upper() != self.CONFIRMATION_TEXT:
            raise UserError(
                _("Escribi %s para confirmar la eliminacion total.")
                % self.CONFIRMATION_TEXT
            )

        run = self.env["lqa.google.merchant.action.run"].sudo().create(
            {
                "user_id": self.env.user.id,
                "action_type": "delete_all",
                "status": "processing",
            }
        )
        try:
            response = self.env["lqa.api.client"].request_absolute_json(
                "POST",
                self._join_url(self._products_base_url(), self.DELETE_ALL_PATH),
                timeout=self._timeout(),
            )
            payload = response if isinstance(response, (dict, list)) else {}
            message = self._clean(
                (
                    payload.get("message")
                    or payload.get("detail")
                    or payload.get("description")
                )
                if isinstance(payload, dict)
                else ""
            ) or "La eliminacion total fue enviada correctamente."
            response_status = (
                self._clean(payload.get("status") or payload.get("state")).upper()
                if isinstance(payload, dict)
                else ""
            )
            failed = bool(
                isinstance(payload, dict)
                and (
                    payload.get("success") is False
                    or response_status in {"ERROR", "FAILED", "FAILURE"}
                )
            )
            run.write(
                {
                    "status": "failed" if failed else "completed",
                    "message": "" if failed else message,
                    "error_message": message if failed else "",
                    "response_json": json.dumps(
                        payload,
                        ensure_ascii=False,
                        default=str,
                    ),
                    "finished_at": fields.Datetime.now(),
                }
            )
        except UserError as error:
            run.write(
                {
                    "status": "failed",
                    "error_message": str(error),
                    "finished_at": fields.Datetime.now(),
                }
            )
        return run.to_panel_dict()

    @api.model
    def delete_selected_products(self, products):
        self._check_access()
        normalized = self._normalize_delete_products(products)
        run = self._create_delete_run(normalized, source_type="manual")
        if len(normalized) == 1:
            self.process_delete_run(run.id, line_limit=1)
        return run.to_panel_dict()

    @api.model
    def delete_products_from_file(self, filename, content_base64):
        self._check_access()
        products = self._parse_delete_file(filename, content_base64)
        run = self._create_delete_run(products, source_type="file", filename=filename)
        return run.to_panel_dict()

    @api.model
    def download_delete_catalog_xlsx(self):
        self._check_access()
        rows = self._google_catalog_delete_rows()
        if not rows:
            raise UserError(_("No encontre productos de Google Merchant para descargar."))
        content = self._build_delete_catalog_xlsx(rows)
        return {
            "filename": "google-merchant-catalogo-eliminador.xlsx",
            "content": base64.b64encode(content).decode("ascii"),
            "mimetype": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            "total": len(rows),
        }

    @api.model
    def process_delete_run(self, run_id, line_limit=50):
        run = (
            self.env["lqa.google.merchant.action.run"]
            .sudo()
            .browse(self._as_int(run_id, 0))
            .exists()
        )
        if not run or run.action_type != "delete_selected":
            return {}

        line_limit = min(max(self._as_int(line_limit, 50), 1), 200)
        lines = run.line_ids.filtered(
            lambda line: line.status in ("pending", "processing")
        )[:line_limit]
        for line in lines:
            line.write(
                {
                    "status": "processing",
                    "started_at": fields.Datetime.now(),
                    "error_message": "",
                }
            )
            try:
                response = self._delete_one_product(
                    line.sku,
                    line.content_language,
                    line.feed_label,
                )
                line.write(
                    {
                        "status": "completed",
                        "message": _("Producto eliminado correctamente."),
                        "response_json": json.dumps(
                            response,
                            ensure_ascii=False,
                            default=str,
                        ),
                        "finished_at": fields.Datetime.now(),
                    }
                )
            except UserError as error:
                line.write(
                    {
                        "status": "failed",
                        "error_message": str(error),
                        "finished_at": fields.Datetime.now(),
                    }
                )
        self._update_delete_run(run)
        return run.to_panel_dict()

    @api.model
    def get_history(self, limit=30):
        self._check_access()
        limit = min(max(self._as_int(limit, 30), 1), 100)
        runs = self.env["lqa.google.merchant.action.run"].sudo().search(
            [],
            order="triggered_at desc, id desc",
            limit=limit,
        )
        return [run.to_panel_dict() for run in runs]

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(
                _("No tenes permisos para ejecutar acciones de Google Merchant.")
            )

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

    def _marketplace_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param(
                "lqa_admin_panel.google_merchant_marketplace_api_url",
                "",
            )
            or os.environ.get("NEXT_PUBLIC_MARKETPLACE_API_URL")
            or os.environ.get("MARKETPLACE_API_URL")
            or self.DEFAULT_MARKETPLACE_API_URL
        ).strip()

    def _trigger_products_job(self, path, payload):
        url = self._join_url(self._products_base_url(), path)
        try:
            response = requests.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(5, self._trigger_timeout()),
            )
            response.raise_for_status()
        except requests.ReadTimeout:
            raise
        except requests.RequestException as error:
            raise UserError(_("No se pudo conectar con Products API: %s") % error) from error

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw_response": response.text}

    def _timeout(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.retailers_timeout_seconds",
                self.DEFAULT_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(value, self.DEFAULT_TIMEOUT_SECONDS), 30), 300)

    def _trigger_timeout(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.google_merchant_trigger_timeout_seconds",
                self.DEFAULT_TRIGGER_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(value, self.DEFAULT_TRIGGER_TIMEOUT_SECONDS), 1), 30)

    def _response_message(self, payload):
        if not isinstance(payload, dict):
            return ""
        return self._clean(
            payload.get("message")
            or payload.get("detail")
            or payload.get("description")
            or payload.get("error")
        )

    def _delete_one_product(self, sku, content_language, feed_label):
        path = self.DELETE_ONE_PATH.format(sku=quote(self._clean(sku), safe=""))
        return self.env["lqa.api.client"].request_absolute_json(
            "DELETE",
            self._join_url(self._marketplace_base_url(), path),
            params={
                "contentLanguage": self._clean(content_language) or "es",
                "feedLabel": self._clean(feed_label) or "AR",
            },
            timeout=self._timeout(),
        )

    def _create_delete_run(self, products, source_type="manual", filename=""):
        run = self.env["lqa.google.merchant.action.run"].sudo().create(
            {
                "user_id": self.env.user.id,
                "action_type": "delete_selected",
                "status": "processing",
                "requested_count": len(products),
                "message": _("Eliminacion en cola. Se procesa producto por producto."),
                "response_json": json.dumps(
                    {
                        "source": source_type,
                        "filename": self._clean(filename),
                        "requested_count": len(products),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "sequence": index * 10,
                            "sku": product["sku"],
                            "content_language": product["content_language"],
                            "feed_label": product["feed_label"],
                        },
                    )
                    for index, product in enumerate(products, start=1)
                ],
            }
        )
        self._update_delete_run(run)
        return run

    def _google_catalog_delete_rows(self):
        rows = []
        seen = set()
        offset = 0
        limit = 500
        max_rows = 100000
        retailers_service = self.env["lqa.retailers.service"].sudo()
        while True:
            response = self.env["lqa.api.client"].request_absolute_json(
                "GET",
                self._join_url(self._madre_base_url(), self.GOOGLE_CATALOG_PATH),
                params={
                    "marketplace": "google-merchant",
                    "offset": offset,
                    "limit": limit,
                },
                timeout=self._timeout(),
            )
            payload = response if isinstance(response, dict) else {}
            items = self._response_items(response)
            for item in items:
                product = retailers_service._normalize_product(
                    item,
                    "google-merchant",
                )
                sku, content_language, feed_label = self._delete_identity_from_product(
                    product
                )
                if not sku:
                    continue
                key = (sku.lower(), content_language.lower(), feed_label.upper())
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "sku": sku,
                        "content_language": content_language,
                        "feed_label": feed_label,
                    }
                )
                if len(rows) >= max_rows:
                    return rows

            has_next = bool(payload.get("hasNext"))
            next_offset = payload.get("nextOffset")
            if not has_next or not items:
                break
            offset = (
                self._as_int(next_offset, offset + limit)
                if next_offset is not None
                else offset + limit
            )
        return rows

    def _delete_identity_from_product(self, product):
        product = product if isinstance(product, dict) else {}
        sku = self._clean(
            product.get("offer_id")
            or product.get("google_product_key")
            or product.get("external_id")
            or product.get("sku")
            or product.get("id")
        )
        content_language = self._clean(product.get("content_language") or "es")
        feed_label = self._clean(product.get("feed_label") or "AR")
        sku, content_language, feed_label = self._split_product_input_id(
            sku,
            content_language,
            feed_label,
        )
        return sku, content_language, feed_label

    def _build_delete_catalog_xlsx(self, rows):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(
            output,
            {
                "in_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
            },
        )
        worksheet = workbook.add_worksheet("Google Merchant")
        header = workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#FF4F5A",
                "border": 1,
                "align": "center",
            }
        )
        text = workbook.add_format({"num_format": "@"})
        columns = (
            ("ID de producto", "sku", 26),
            ("Etiqueta de feed", "feed_label", 18),
            ("Idioma", "content_language", 12),
        )
        for index, (label, _key, width) in enumerate(columns):
            worksheet.write(0, index, label, header)
            worksheet.set_column(index, index, width, text)
        for row_index, row in enumerate(rows, start=1):
            worksheet.write_string(row_index, 0, row.get("sku") or "", text)
            worksheet.write_string(row_index, 1, row.get("feed_label") or "AR", text)
            worksheet.write_string(
                row_index,
                2,
                row.get("content_language") or "es",
                text,
            )
        worksheet.autofilter(0, 0, len(rows), len(columns) - 1)
        worksheet.freeze_panes(1, 0)
        workbook.close()
        return output.getvalue()

    def _update_delete_run(self, run):
        run = run.sudo()
        deleted_count = len(run.line_ids.filtered(lambda line: line.status == "completed"))
        failed_count = len(run.line_ids.filtered(lambda line: line.status == "failed"))
        pending_count = len(
            run.line_ids.filtered(lambda line: line.status in ("pending", "processing"))
        )
        requested_count = len(run.line_ids)
        if pending_count:
            status = "processing"
            message = _("%s de %s productos procesados. Quedan %s en cola.") % (
                deleted_count + failed_count,
                requested_count,
                pending_count,
            )
            finished_at = False
        elif failed_count and failed_count == requested_count:
            status = "failed"
            message = ""
            finished_at = fields.Datetime.now()
        elif failed_count:
            status = "partial"
            message = _("%s productos eliminados y %s con error.") % (
                deleted_count,
                failed_count,
            )
            finished_at = fields.Datetime.now()
        else:
            status = "completed"
            message = _("%s productos eliminados correctamente.") % deleted_count
            finished_at = fields.Datetime.now()
        response_payload = {
            "requested_count": requested_count,
            "deleted_count": deleted_count,
            "failed_count": failed_count,
            "pending_count": pending_count,
            "line_preview": [
                line.to_panel_dict()
                for line in run.line_ids.sorted(lambda item: (item.sequence, item.id))[:50]
            ],
        }
        first_failed = run.line_ids.filtered(lambda line: line.status == "failed")[:1]
        run.write(
            {
                "status": status,
                "message": message,
                "requested_count": requested_count,
                "deleted_count": deleted_count,
                "failed_count": failed_count,
                "error_message": first_failed.error_message
                if status == "failed" and first_failed
                else "",
                "finished_at": finished_at,
                "response_json": json.dumps(
                    response_payload,
                    ensure_ascii=False,
                    default=str,
                ),
            }
        )

    def _parse_delete_file(self, filename, content_base64):
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
            raise UserError(_("Usa un archivo CSV o XLSX."))
        return self._delete_products_from_rows(rows)

    def _delete_products_from_rows(self, rows):
        rows = [row for row in rows if any(self._clean(value) for value in row)]
        if not rows:
            raise UserError(_("El archivo no contiene datos."))
        headers = [self._normalize_header(value) for value in rows[0]]
        sku_index = self._find_header_index(headers, self.PRODUCT_ID_HEADERS)
        feed_index = self._find_header_index(headers, self.FEED_LABEL_HEADERS)
        language_index = self._find_header_index(headers, self.CONTENT_LANGUAGE_HEADERS)
        has_headers = sku_index >= 0
        if not has_headers:
            sku_index = 0
            feed_index = 1 if len(rows[0]) > 1 else -1
            language_index = 2 if len(rows[0]) > 2 else -1

        products = []
        data_rows = rows[1:] if has_headers else rows
        for row_number, row in enumerate(data_rows, start=2 if has_headers else 1):
            sku = self._cell(row, sku_index)
            feed_label = self._cell(row, feed_index) if feed_index >= 0 else "AR"
            content_language = (
                self._cell(row, language_index) if language_index >= 0 else "es"
            )
            if not sku and not feed_label and not content_language:
                continue
            if not sku:
                raise UserError(_("Fila %s incompleta: falta ID de producto.") % row_number)
            products.append(
                {
                    "sku": sku,
                    "feedLabel": feed_label or "AR",
                    "contentLanguage": content_language or "es",
                }
            )
            if len(products) > self.MAX_DELETE_ROWS:
                raise UserError(
                    _("El archivo supera el limite de %s productos.")
                    % self.MAX_DELETE_ROWS
                )
        return self._normalize_delete_products(products)

    def _normalize_delete_products(self, products):
        if not isinstance(products, list):
            raise UserError(_("El listado de productos no es valido."))
        normalized = []
        seen = set()
        for item in products:
            item = item if isinstance(item, dict) else {}
            sku = self._clean(
                item.get("sku")
                or item.get("productId")
                or item.get("product_id")
                or item.get("id")
                or item.get("offerId")
            )
            content_language = self._clean(
                item.get("contentLanguage")
                or item.get("content_language")
                or item.get("language")
                or item.get("idioma")
                or "es"
            ).lower()
            feed_label = self._clean(
                item.get("feedLabel")
                or item.get("feed_label")
                or item.get("feed")
                or item.get("etiquetaFeed")
                or "AR"
            ).upper()
            sku, content_language, feed_label = self._split_product_input_id(
                sku,
                content_language,
                feed_label,
            )
            if not sku:
                raise UserError(_("Cada producto requiere SKU o ID de producto."))
            key = (sku.lower(), content_language.lower(), feed_label.upper())
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "sku": sku,
                    "content_language": content_language or "es",
                    "feed_label": feed_label or "AR",
                }
            )
        if not normalized:
            raise UserError(_("Ingresa al menos un producto para eliminar."))
        if len(normalized) > self.MAX_DELETE_ROWS:
            raise UserError(
                _("No se pueden encolar mas de %s productos por importacion.")
                % self.MAX_DELETE_ROWS
            )
        return normalized

    def _split_product_input_id(self, sku, content_language, feed_label):
        sku = self._clean(sku)
        if "/products/" in sku:
            sku = sku.rsplit("/products/", 1)[-1]

        parts = [self._clean(part) for part in sku.split("~")]
        if len(parts) >= 3:
            content_language = parts[0] or content_language
            feed_label = parts[1] or feed_label
            sku = "~".join(parts[2:]) or sku
        return (
            sku,
            self._clean(content_language).lower() or "es",
            self._clean(feed_label).upper() or "AR",
        )

    def _read_csv_rows(self, content):
        text = ""
        for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            raise UserError(_("No se pudo leer el CSV."))
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel_tab if "\t" in sample else csv.excel
        return list(csv.reader(io.StringIO(text), dialect))

    def _response_items(self, response):
        if isinstance(response, list):
            return response
        if not isinstance(response, dict):
            return []
        for key in ("items", "products", "data", "results"):
            value = response.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = self._response_items(value)
                if nested:
                    return nested
        return []

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

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    @staticmethod
    def _as_int(value, default):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_header(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())

    @staticmethod
    def _find_header_index(headers, candidates):
        for index, header in enumerate(headers):
            if header in candidates:
                return index
        return -1

    @classmethod
    def _cell(cls, row, index):
        return cls._clean(row[index]) if 0 <= index < len(row) else ""

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
    def _join_url(base, path):
        return "/".join([str(base or "").rstrip("/"), str(path or "").lstrip("/")])
