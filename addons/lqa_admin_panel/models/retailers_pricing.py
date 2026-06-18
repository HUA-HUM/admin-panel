import base64
import io
import json
import os
import posixpath
import re
import zipfile
from xml.etree import ElementTree

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaRetailersPricingJob(models.Model):
    _name = "lqa.retailers.pricing.job"
    _description = "Job de pricing Retailers"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, default="Pricing Retailers")
    user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    state = fields.Selection(
        [
            ("pending", "En cola"),
            ("processing", "Procesando"),
            ("done", "Listo"),
            ("failed", "Error"),
        ],
        default="pending",
        required=True,
        readonly=True,
        index=True,
    )
    source_type = fields.Selection(
        [("xlsx", "Excel"), ("manual", "Manual")],
        required=True,
        default="xlsx",
        readonly=True,
    )
    input_filename = fields.Char(readonly=True)
    input_count = fields.Integer(readonly=True)
    success_count = fields.Integer(readonly=True)
    failed_count = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    line_ids = fields.One2many(
        "lqa.retailers.pricing.item",
        "job_id",
        readonly=True,
    )

    @api.model
    def _cron_process_pending_jobs(self, limit=2):
        jobs = self.search(
            [("state", "=", "pending")],
            order="create_date asc, id asc",
            limit=limit,
        )
        service = self.env["lqa.retailers.pricing.service"].sudo()
        for job in jobs:
            service.process_job(job.id)


class LqaRetailersPricingItem(models.Model):
    _name = "lqa.retailers.pricing.item"
    _description = "Item de pricing Retailers"
    _order = "sequence asc, id asc"

    job_id = fields.Many2one(
        "lqa.retailers.pricing.job",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    state = fields.Selection(
        [
            ("pending", "En cola"),
            ("done", "Listo"),
            ("failed", "Error"),
        ],
        default="pending",
        required=True,
        readonly=True,
    )
    sku = fields.Char(index=True)
    sale_price = fields.Float()
    sales_channel = fields.Char(index=True)
    input_payload_json = fields.Text(readonly=True)
    response_json = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)

    def to_panel_dict(self):
        self.ensure_one()
        response = self._json_loads(self.response_json)
        prices = response.get("prices") or {}
        resultados = response.get("resultados") or {}
        precio = response.get("precio") or {}
        status = response.get("status") or {}
        return {
            "id": self.id,
            "state": self.state,
            "sku": self.sku or "",
            "salePrice": self.sale_price,
            "salesChannel": self.sales_channel or "",
            "sellerNetPrice": prices.get("sellerNetPrice"),
            "totalCosts": resultados.get("totalCosts"),
            "operatingProfit": resultados.get("operatingProfit"),
            "operatingProfitPercent": resultados.get("operatingProfitPercent"),
            "suggestedPrice": precio.get("suggestedPrice"),
            "discount": precio.get("discount"),
            "profitable": status.get("profitable"),
            "shouldPause": status.get("shouldPause"),
            "errorMessage": self.error_message or "",
        }

    @staticmethod
    def _json_loads(value):
        if not value:
            return {}
        try:
            return json.loads(value)
        except ValueError:
            return {}


class LqaRetailersPricingService(models.AbstractModel):
    _name = "lqa.retailers.pricing.service"
    _description = "Servicio de pricing Retailers"

    DEFAULT_ENDPOINT = (
        "https://api.price.loquieroaca.com/"
        "internal/getProfit/channel/details/bulk"
    )
    ALLOWED_CHANNELS = ("fravega", "megatone", "oncity")
    MAX_ITEMS = 5000
    MAX_UPLOAD_BYTES = 20 * 1024 * 1024
    MAX_XLSX_XML_BYTES = 40 * 1024 * 1024
    REQUEST_CHUNK_SIZE = 100
    XLSX_OUTPUT_COLUMNS = (
        ("SKU", "input.sku", "text", 18),
        ("Canal", "input.salesChannel", "text", 15),
        ("Precio venta", "input.salePrice", "money", 16),
        ("Estado fila", "state", "text", 13),
        ("Error", "error", "text", 34),
        ("Precio venta API", "prices.salePrice", "money", 17),
        (
            "Aporte canal %",
            "prices.meliContributionPercentage",
            "percentage_points",
            17,
        ),
        ("Aporte canal monto", "prices.meliContributionAmount", "money", 18),
        ("Precio neto vendedor", "prices.sellerNetPrice", "money", 20),
        ("Peso kg", "datosBase.weightKg", "decimal", 12),
        ("Peso volumetrico kg", "datosBase.volumetricWeightKg", "decimal", 20),
        ("Precio neto base", "datosBase.sellerNetPrice", "money", 18),
        ("Categoria", "datosBase.categoryId", "text", 18),
        ("TC AMCO", "tiposDeCambio.tcAmco", "decimal", 12),
        ("TC TLQ", "tiposDeCambio.tcTlq", "decimal", 12),
        (
            "Comision canal %",
            "costosOperativos.commissionMpPercentage",
            "percentage_points",
            18,
        ),
        ("Envio", "costosOperativos.envioMlAmount", "money", 15),
        ("Precio Amazon", "costosOperativos.precioAmzAmount", "money", 17),
        ("Deposito USA", "costosOperativos.depositoUsaAmount", "money", 17),
        ("Costos AMCO", "costosOperativos.costosAmcoAmount", "money", 17),
        ("Impuestos AMCO", "costosOperativos.imptosAmcoAmount", "money", 18),
        ("IVA cat. arancelaria", "emo.ivaCatAranc", "percentage_decimal", 19),
        ("Tasas y derechos", "emo.sumaTasasYDer", "percentage_decimal", 18),
        ("Utilidad calculada", "costosCalculados.utilidadAmount", "money", 19),
        ("Impuestos", "costosCalculados.impuestosMeliAmount", "money", 16),
        ("Comision", "costosCalculados.comisionMpAmount", "money", 16),
        ("Costos totales", "resultados.totalCosts", "money", 18),
        ("Ganancia operativa", "resultados.operatingProfit", "money", 20),
        (
            "Margen operativo",
            "resultados.operatingProfitPercent",
            "percentage_text",
            18,
        ),
        ("Precio sugerido", "precio.suggestedPrice", "money", 18),
        ("Descuento", "precio.discount", "percentage_text", 14),
        ("Rentable", "status.profitable", "boolean", 12),
        ("Debe pausar", "status.shouldPause", "boolean", 14),
    )

    @api.model
    def create_manual_job(self, sku, sale_price, sales_channel):
        self._check_access()
        row = self._normalize_row(
            {
                "sku": sku,
                "salePrice": sale_price,
                "salesChannel": sales_channel,
            }
        )
        return self._create_job([row], "manual", "")

    @api.model
    def create_xlsx_job(self, filename, content_base64):
        self._check_access()
        rows = self._parse_xlsx(filename, content_base64)
        return self._create_job(rows, "xlsx", filename)

    @api.model
    def get_jobs(self, limit=30):
        self._check_access()
        limit = min(max(self._as_int(limit, 30), 1), 100)
        domain = []
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_admin"):
            domain.append(("user_id", "=", self.env.user.id))
        jobs = self.env["lqa.retailers.pricing.job"].search(
            domain,
            order="create_date desc, id desc",
            limit=limit,
        )
        return [self._job_to_dict(job) for job in jobs]

    @api.model
    def get_job(self, job_id):
        self._check_access()
        return self._job_to_dict(self._get_job(job_id), include_lines=True)

    @api.model
    def process_job(self, job_id):
        job = self.env["lqa.retailers.pricing.job"].browse(
            self._as_int(job_id, 0)
        ).exists()
        if not job or job.state != "pending":
            return {}
        job.write(
            {
                "state": "processing",
                "started_at": fields.Datetime.now(),
                "error_message": "",
            }
        )
        try:
            self._process_job_lines(job)
            self._finish_job(job)
        except Exception as error:
            message = str(error)
            job.line_ids.filtered(lambda line: line.state == "pending").write(
                {"state": "failed", "error_message": message}
            )
            job.write(
                {
                    "state": "failed",
                    "failed_count": job.input_count,
                    "error_message": message,
                    "finished_at": fields.Datetime.now(),
                }
            )
        return self._job_to_dict(job)

    @api.model
    def download_template_xlsx(self):
        self._check_access()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(
            output,
            {
                "in_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
            },
        )
        worksheet = workbook.add_worksheet("Pricing Retailers")
        header = workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#FF4F5A",
                "border": 1,
                "align": "center",
            }
        )
        money = workbook.add_format({"num_format": "$ #,##0.00"})
        columns = ("sku", "salePrice", "salesChannel")
        for index, value in enumerate(columns):
            worksheet.write(0, index, value, header)
        worksheet.write(1, 0, "B0F47N62NN")
        worksheet.write_number(1, 1, 731399, money)
        worksheet.write(1, 2, "megatone")
        worksheet.write(2, 0, "B08S348KVR")
        worksheet.write_number(2, 1, 236999, money)
        worksheet.write(2, 2, "fravega")
        worksheet.set_column(0, 0, 20)
        worksheet.set_column(1, 1, 18)
        worksheet.set_column(2, 2, 18)
        worksheet.autofilter(0, 0, 2, 2)
        workbook.close()
        return {
            "filename": "retailers-pricing-plantilla.xlsx",
            "content": base64.b64encode(output.getvalue()).decode("ascii"),
            "mimetype": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        }

    @api.model
    def download_job_xlsx(self, job_id):
        self._check_access()
        job = self._get_job(job_id)
        content = self._build_result_xlsx(job)
        return {
            "filename": f"{self._safe_name(job.name)}-resultado.xlsx",
            "content": base64.b64encode(content).decode("ascii"),
            "mimetype": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        }

    def _create_job(self, rows, source_type, filename):
        if not rows:
            raise UserError(_("No encontre filas validas para procesar."))
        if len(rows) > self.MAX_ITEMS:
            raise UserError(_("Podes procesar hasta %s filas por job.") % self.MAX_ITEMS)
        job = self.env["lqa.retailers.pricing.job"].sudo().create(
            {
                "name": (
                    filename
                    or f"Pricing manual {fields.Datetime.now()}"
                ),
                "user_id": self.env.user.id,
                "source_type": source_type,
                "input_filename": filename or "",
                "input_count": len(rows),
                "line_ids": [
                    fields.Command.create(self._line_values(row, index))
                    for index, row in enumerate(rows, start=1)
                ],
            }
        )
        return self._job_to_dict(job)

    def _process_job_lines(self, job):
        endpoint, api_key, timeout = self._pricing_config()
        client = self.env["lqa.api.client"]
        lines = job.line_ids.sorted("sequence")
        for chunk in self._chunks(lines, self.REQUEST_CHUNK_SIZE):
            payload = [json.loads(line.input_payload_json) for line in chunk]
            response = client.request_absolute_json(
                "POST",
                endpoint,
                payload=payload,
                params={"page": 1, "perPage": len(payload)},
                headers={"x-api-key": api_key},
                timeout=timeout,
            )
            items = response.get("items") if isinstance(response, dict) else []
            items = items if isinstance(items, list) else []
            for index, line in enumerate(chunk):
                item = items[index] if index < len(items) else {}
                if item:
                    line.write(
                        {
                            "state": "done",
                            "response_json": json.dumps(
                                item,
                                ensure_ascii=False,
                                default=str,
                            ),
                            "error_message": "",
                        }
                    )
                else:
                    line.write(
                        {
                            "state": "failed",
                            "error_message": _(
                                "La API no devolvio resultado para esta fila."
                            ),
                        }
                    )

    def _finish_job(self, job):
        success_count = len(job.line_ids.filtered(lambda line: line.state == "done"))
        failed_count = len(job.line_ids.filtered(lambda line: line.state == "failed"))
        job.write(
            {
                "state": "done" if success_count else "failed",
                "success_count": success_count,
                "failed_count": failed_count,
                "finished_at": fields.Datetime.now(),
            }
        )

    def _parse_xlsx(self, filename, content_base64):
        filename = self._clean(filename)
        if not filename.lower().endswith(".xlsx"):
            raise UserError(_("Selecciona un archivo de Excel XLSX."))
        try:
            content = base64.b64decode(content_base64 or "", validate=True)
        except (TypeError, ValueError) as error:
            raise UserError(_("El archivo recibido no es valido.")) from error
        if not content:
            raise UserError(_("El archivo esta vacio."))
        if len(content) > self.MAX_UPLOAD_BYTES:
            raise UserError(_("El archivo no puede superar 20 MB."))
        rows = self._read_xlsx_rows(content)
        rows = [row for row in rows if any(self._clean(value) for value in row)]
        if not rows:
            raise UserError(_("El Excel no contiene datos."))
        headers = [self._normalize_header(value) for value in rows[0]]
        indexes = {
            "sku": self._find_header_index(headers, {"sku"}),
            "salePrice": self._find_header_index(
                headers,
                {"saleprice", "precio", "precioventa", "price"},
            ),
            "salesChannel": self._find_header_index(
                headers,
                {"saleschannel", "canal", "marketplace", "channel"},
            ),
        }
        missing_headers = [key for key, index in indexes.items() if index < 0]
        if missing_headers:
            raise UserError(
                _("El Excel debe incluir sku, salePrice y salesChannel.")
            )
        parsed = []
        for row_number, row in enumerate(rows[1:], start=2):
            values = {
                key: self._cell(row, index)
                for key, index in indexes.items()
            }
            if not any(values.values()):
                continue
            try:
                parsed.append(self._normalize_row(values))
            except UserError as error:
                raise UserError(_("Fila %s: %s") % (row_number, error)) from error
            if len(parsed) > self.MAX_ITEMS:
                raise UserError(
                    _("El Excel supera el limite de %s filas.") % self.MAX_ITEMS
                )
        return parsed

    def _normalize_row(self, row):
        sku = self._clean(self._pick(row, "sku"))
        sale_price = self._as_float(
            self._pick(row, "salePrice", "sale_price", "precio", "price"),
            None,
        )
        sales_channel = self._clean(
            self._pick(
                row,
                "salesChannel",
                "sales_channel",
                "canal",
                "marketplace",
            )
        ).lower()
        if not sku:
            raise UserError(_("El SKU es obligatorio."))
        if sale_price is None or sale_price <= 0:
            raise UserError(_("El precio de venta debe ser mayor a cero."))
        if sales_channel not in self.ALLOWED_CHANNELS:
            raise UserError(
                _("El canal debe ser fravega, megatone u oncity.")
            )
        return {
            "sku": sku,
            "salePrice": sale_price,
            "salesChannel": sales_channel,
        }

    def _line_values(self, row, index):
        return {
            "sequence": index,
            "sku": row["sku"],
            "sale_price": row["salePrice"],
            "sales_channel": row["salesChannel"],
            "input_payload_json": json.dumps(
                row,
                ensure_ascii=False,
                default=str,
            ),
        }

    def _build_result_xlsx(self, job):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(
            output,
            {
                "in_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
            },
        )
        worksheet = workbook.add_worksheet("Pricing Retailers")
        worksheet.hide_gridlines(2)
        worksheet.freeze_panes(1, 0)
        formats = {
            "header": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": "#FF4F5A",
                    "border": 1,
                    "align": "center",
                }
            ),
            "text": workbook.add_format({"valign": "top"}),
            "error": workbook.add_format(
                {
                    "font_color": "#A22B2B",
                    "bg_color": "#FFF0F0",
                    "text_wrap": True,
                    "valign": "top",
                }
            ),
            "money": workbook.add_format(
                {"num_format": "$ #,##0.00;[Red]-$ #,##0.00"}
            ),
            "decimal": workbook.add_format({"num_format": "#,##0.00"}),
            "percentage": workbook.add_format({"num_format": "0.00%"}),
        }
        for index, (header, _, _, width) in enumerate(self.XLSX_OUTPUT_COLUMNS):
            worksheet.write(0, index, header, formats["header"])
            worksheet.set_column(index, index, width)
        for row_index, line in enumerate(job.line_ids.sorted("sequence"), start=1):
            source = self._result_row_source(line)
            for column_index, (_, path, value_type, _) in enumerate(
                self.XLSX_OUTPUT_COLUMNS
            ):
                self._write_xlsx_value(
                    worksheet,
                    row_index,
                    column_index,
                    self._nested_value(source, path),
                    value_type,
                    formats,
                    is_error_column=path == "error",
                )
        worksheet.autofilter(
            0,
            0,
            max(len(job.line_ids), 1),
            len(self.XLSX_OUTPUT_COLUMNS) - 1,
        )
        workbook.close()
        return output.getvalue()

    def _result_row_source(self, line):
        response = self._json_loads(line.response_json)
        return {
            "input": self._json_loads(line.input_payload_json),
            "state": {
                "pending": "En cola",
                "done": "Listo",
                "failed": "Error",
            }.get(line.state, line.state),
            "error": line.error_message or "",
            **response,
        }

    def _write_xlsx_value(
        self,
        worksheet,
        row,
        column,
        value,
        value_type,
        formats,
        is_error_column=False,
    ):
        if value in (None, ""):
            worksheet.write_blank(row, column, None, formats["text"])
            return
        if value_type in {"money", "decimal"}:
            numeric = self._as_float(value, None)
            if numeric is not None:
                worksheet.write_number(row, column, numeric, formats[value_type])
                return
        if value_type == "percentage_points":
            numeric = self._as_float(value, None)
            if numeric is not None:
                worksheet.write_number(
                    row, column, numeric / 100, formats["percentage"]
                )
                return
        if value_type == "percentage_decimal":
            numeric = self._as_float(value, None)
            if numeric is not None:
                worksheet.write_number(
                    row, column, numeric, formats["percentage"]
                )
                return
        if value_type == "percentage_text":
            numeric = self._percentage_decimal(value)
            if numeric is not None:
                worksheet.write_number(
                    row, column, numeric, formats["percentage"]
                )
                return
        if value_type == "boolean":
            worksheet.write(
                row,
                column,
                "Si" if bool(value) else "No",
                formats["text"],
            )
            return
        worksheet.write(
            row,
            column,
            str(value),
            formats["error"] if is_error_column and value else formats["text"],
        )

    def _pricing_config(self):
        params = self.env["ir.config_parameter"].sudo()
        endpoint = (
            params.get_param("lqa_admin_panel.retailers_pricing_url")
            or os.environ.get("LQA_RETAILERS_PRICING_URL")
            or self.DEFAULT_ENDPOINT
        )
        api_key = (
            params.get_param("lqa_admin_panel.retailers_pricing_api_key")
            or os.environ.get("LQA_RETAILERS_PRICING_API_KEY")
            or params.get_param("lqa_admin_panel.mercadolibre_pricing_api_key")
            or os.environ.get("LQA_MERCADOLIBRE_PRICING_API_KEY")
        )
        timeout = self._as_int(
            params.get_param("lqa_admin_panel.retailers_pricing_timeout_seconds")
            or os.environ.get("LQA_RETAILERS_PRICING_TIMEOUT_SECONDS"),
            self._as_int(
                params.get_param(
                    "lqa_admin_panel.mercadolibre_pricing_timeout_seconds"
                )
                or os.environ.get(
                    "LQA_MERCADOLIBRE_PRICING_TIMEOUT_SECONDS"
                ),
                300,
            ),
        )
        if not endpoint or not api_key:
            raise UserError(_("Configura la URL y API key de Pricing Retailers."))
        return endpoint, api_key, timeout

    def _get_job(self, job_id):
        job = self.env["lqa.retailers.pricing.job"].browse(
            self._as_int(job_id, 0)
        ).exists()
        if not job:
            raise UserError(_("El job de pricing no existe."))
        if (
            not self.env.user.has_group("lqa_admin_panel.group_lqa_admin")
            and job.user_id != self.env.user
        ):
            raise AccessError(_("No tenes permisos para ver este job."))
        return job

    def _job_to_dict(self, job, include_lines=False):
        data = {
            "id": job.id,
            "name": job.name,
            "state": job.state,
            "sourceType": job.source_type,
            "filename": job.input_filename or "",
            "inputCount": job.input_count,
            "successCount": job.success_count,
            "failedCount": job.failed_count,
            "errorMessage": job.error_message or "",
            "createdAt": fields.Datetime.to_string(job.create_date),
            "startedAt": fields.Datetime.to_string(job.started_at),
            "finishedAt": fields.Datetime.to_string(job.finished_at),
            "userName": job.user_id.name,
            "canDownload": job.state in {"done", "failed"},
        }
        if include_lines:
            data["lines"] = [line.to_panel_dict() for line in job.line_ids]
        return data

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
            self._check_xlsx_entry_size(workbook, sheet_path)
            try:
                root = ElementTree.fromstring(workbook.read(sheet_path))
            except (KeyError, ElementTree.ParseError) as error:
                raise UserError(_("No se pudo leer el Excel.")) from error
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows = []
        for row in root.findall(".//x:sheetData/x:row", namespace):
            values = {}
            max_column = -1
            for cell in row.findall("x:c", namespace):
                column = self._xlsx_column_index(cell.get("r", ""))
                if column < 0:
                    continue
                values[column] = self._xlsx_cell_value(
                    cell,
                    shared_strings,
                    namespace,
                )
                max_column = max(max_column, column)
            if max_column >= 0:
                rows.append(
                    [values.get(index, "") for index in range(max_column + 1)]
                )
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
        return value

    def _check_xlsx_entry_size(self, workbook, path):
        try:
            size = workbook.getinfo(path).file_size
        except KeyError as error:
            raise UserError(_("El XLSX esta incompleto.")) from error
        if size > self.MAX_XLSX_XML_BYTES:
            raise UserError(_("El contenido interno del XLSX es demasiado grande."))

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(_("No tenes permisos para usar Pricing Retailers."))

    @staticmethod
    def _chunks(records, size):
        records = list(records)
        for index in range(0, len(records), size):
            yield records[index : index + size]

    @staticmethod
    def _pick(row, *keys):
        lowered = {str(key).strip().lower(): value for key, value in row.items()}
        for key in keys:
            value = lowered.get(str(key).strip().lower())
            if value not in (None, ""):
                return value
        return ""

    @staticmethod
    def _nested_value(source, path):
        current = source
        for key in path.split("."):
            if not isinstance(current, dict):
                return ""
            current = current.get(key)
        return "" if current is None else current

    @staticmethod
    def _json_loads(value):
        if not value:
            return {}
        try:
            return json.loads(value)
        except ValueError:
            return {}

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
    def _as_int(value, default):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value, default):
        if value in (None, ""):
            return default
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return default

    def _percentage_decimal(self, value):
        clean_value = self._clean(value)
        if not clean_value:
            return None
        numeric = self._as_float(clean_value.rstrip("%").strip(), None)
        if numeric is None:
            return None
        return numeric / 100 if clean_value.endswith("%") or numeric > 1 else numeric

    @staticmethod
    def _clean(value):
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    @staticmethod
    def _safe_name(value):
        clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "")).strip("-")
        return clean or "retailers-pricing"
