import base64
import csv
import io
import json
import os

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaMercadolibrePricingJob(models.Model):
    _name = "lqa.mercadolibre.pricing.job"
    _description = "Job de pricing MercadoLibre"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, default="Pricing MercadoLibre")
    user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    state = fields.Selection(
        selection=[
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
        selection=[("csv", "CSV"), ("manual", "Manual")],
        default="csv",
        required=True,
        readonly=True,
    )
    input_filename = fields.Char(readonly=True)
    input_count = fields.Integer(readonly=True)
    success_count = fields.Integer(readonly=True)
    failed_count = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)
    result_csv = fields.Text(readonly=True)
    notified = fields.Boolean(default=False, readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    line_ids = fields.One2many(
        "lqa.mercadolibre.pricing.item",
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
        service = self.env["lqa.mercadolibre.pricing.service"].sudo()
        for job in jobs:
            service.process_job(job.id)


class LqaMercadolibrePricingItem(models.Model):
    _name = "lqa.mercadolibre.pricing.item"
    _description = "Item de pricing MercadoLibre"
    _order = "sequence asc, id asc"

    job_id = fields.Many2one(
        "lqa.mercadolibre.pricing.job",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    state = fields.Selection(
        selection=[
            ("pending", "En cola"),
            ("done", "Listo"),
            ("failed", "Error"),
        ],
        default="pending",
        required=True,
        readonly=True,
    )
    mla = fields.Char(index=True)
    category_id = fields.Char()
    publication_type = fields.Char()
    sku = fields.Char(index=True)
    sale_price = fields.Float()
    has_meli_contribution = fields.Boolean()
    meli_contribution_percentage = fields.Float()
    input_payload_json = fields.Text(readonly=True)
    response_json = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)

    def to_panel_dict(self):
        self.ensure_one()
        response = self._json_loads(self.response_json)
        resultados = response.get("resultados") or {}
        precio = response.get("precio") or {}
        prices = response.get("prices") or {}
        return {
            "id": self.id,
            "state": self.state,
            "mla": self.mla or "",
            "categoryId": self.category_id or "",
            "publicationType": self.publication_type or "",
            "sku": self.sku or "",
            "salePrice": self.sale_price,
            "meliContributionPercentage": (
                self.meli_contribution_percentage
                if self.has_meli_contribution
                else False
            ),
            "sellerNetPrice": prices.get("sellerNetPrice"),
            "totalCosts": resultados.get("totalCosts"),
            "operatingProfit": resultados.get("operatingProfit"),
            "operatingProfitPercent": resultados.get("operatingProfitPercent"),
            "suggestedPrice": precio.get("suggestedPrice"),
            "discount": precio.get("discount"),
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


class LqaMercadolibrePricingService(models.AbstractModel):
    _name = "lqa.mercadolibre.pricing.service"
    _description = "Servicio de pricing MercadoLibre"

    DEFAULT_ENDPOINT = (
        "https://api.price.loquieroaca.com/internal/getProfit/details/bulk"
    )
    REQUIRED_FIELDS = ("mla", "categoryId", "publicationType", "sku", "salePrice")
    MAX_ITEMS = 5000
    REQUEST_CHUNK_SIZE = 100
    CSV_OUTPUT_COLUMNS = (
        ("mla", "input.mla"),
        ("sku", "input.sku"),
        ("category_id", "input.categoryId"),
        ("publication_type", "input.publicationType"),
        ("sale_price", "input.salePrice"),
        ("meli_contribution_percentage", "input.meliContributionPercentage"),
        ("state", "state"),
        ("error", "error"),
        ("api_sale_price", "prices.salePrice"),
        (
            "api_meli_contribution_percentage",
            "prices.meliContributionPercentage",
        ),
        ("meli_contribution_amount", "prices.meliContributionAmount"),
        ("seller_net_price", "prices.sellerNetPrice"),
        ("base_sku", "datosBase.sku"),
        ("weight_kg", "datosBase.weightKg"),
        ("volumetric_weight_kg", "datosBase.volumetricWeightKg"),
        ("base_seller_net_price", "datosBase.sellerNetPrice"),
        ("base_category_id", "datosBase.categoryId"),
        ("tc_amco", "tiposDeCambio.tcAmco"),
        ("tc_tlq", "tiposDeCambio.tcTlq"),
        ("commission_mp_percentage", "costosOperativos.commissionMpPercentage"),
        ("envio_ml_amount", "costosOperativos.envioMlAmount"),
        ("precio_amz_amount", "costosOperativos.precioAmzAmount"),
        ("deposito_usa_amount", "costosOperativos.depositoUsaAmount"),
        ("costos_amco_amount", "costosOperativos.costosAmcoAmount"),
        ("imptos_amco_amount", "costosOperativos.imptosAmcoAmount"),
        ("iva_cat_aranc", "emo.ivaCatAranc"),
        ("suma_tasas_y_der", "emo.sumaTasasYDer"),
        ("utilidad_amount", "costosCalculados.utilidadAmount"),
        ("impuestos_meli_amount", "costosCalculados.impuestosMeliAmount"),
        ("comision_mp_amount", "costosCalculados.comisionMpAmount"),
        ("total_costs", "resultados.totalCosts"),
        ("operating_profit", "resultados.operatingProfit"),
        ("operating_profit_percent", "resultados.operatingProfitPercent"),
        ("suggested_price", "precio.suggestedPrice"),
        ("discount", "precio.discount"),
    )
    XLSX_OUTPUT_COLUMNS = (
        ("MLA", "input.mla", "text", 18),
        ("SKU", "input.sku", "text", 18),
        ("Categoria", "input.categoryId", "text", 16),
        ("Tipo publicacion", "input.publicationType", "text", 18),
        ("Precio venta", "input.salePrice", "money", 16),
        (
            "Aporte ML %",
            "input.meliContributionPercentage",
            "percentage_points",
            14,
        ),
        ("Estado", "state", "text", 12),
        ("Error", "error", "text", 34),
        ("Precio venta API", "prices.salePrice", "money", 17),
        (
            "Aporte ML % API",
            "prices.meliContributionPercentage",
            "percentage_points",
            17,
        ),
        (
            "Aporte ML monto",
            "prices.meliContributionAmount",
            "money",
            18,
        ),
        ("Precio neto vendedor", "prices.sellerNetPrice", "money", 20),
        ("SKU datos base", "datosBase.sku", "text", 18),
        ("Peso kg", "datosBase.weightKg", "decimal", 12),
        ("Peso volumetrico kg", "datosBase.volumetricWeightKg", "decimal", 20),
        ("Precio neto base", "datosBase.sellerNetPrice", "money", 18),
        ("Categoria datos base", "datosBase.categoryId", "text", 20),
        ("TC AMCO", "tiposDeCambio.tcAmco", "decimal", 12),
        ("TC TLQ", "tiposDeCambio.tcTlq", "decimal", 12),
        (
            "Comision MP %",
            "costosOperativos.commissionMpPercentage",
            "percentage_points",
            16,
        ),
        ("Envio ML", "costosOperativos.envioMlAmount", "money", 15),
        ("Precio Amazon", "costosOperativos.precioAmzAmount", "money", 17),
        ("Deposito USA", "costosOperativos.depositoUsaAmount", "money", 17),
        ("Costos AMCO", "costosOperativos.costosAmcoAmount", "money", 17),
        ("Impuestos AMCO", "costosOperativos.imptosAmcoAmount", "money", 18),
        ("IVA cat. arancelaria", "emo.ivaCatAranc", "percentage_decimal", 19),
        (
            "Tasas y derechos",
            "emo.sumaTasasYDer",
            "percentage_decimal",
            18,
        ),
        ("Utilidad calculada", "costosCalculados.utilidadAmount", "money", 19),
        (
            "Impuestos MercadoLibre",
            "costosCalculados.impuestosMeliAmount",
            "money",
            22,
        ),
        (
            "Comision MercadoPago",
            "costosCalculados.comisionMpAmount",
            "money",
            21,
        ),
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
    )

    @api.model
    def create_job(self, source_type="csv", content="", filename=""):
        self._check_access()
        rows = self._parse_input(content)
        if not rows:
            raise UserError(_("No encontre filas validas para procesar."))
        if len(rows) > self.MAX_ITEMS:
            raise UserError(_("Podes procesar hasta %s filas por job.") % self.MAX_ITEMS)

        job = self.env["lqa.mercadolibre.pricing.job"].sudo().create(
            {
                "name": self._job_name(source_type, filename),
                "user_id": self.env.user.id,
                "source_type": source_type if source_type in {"csv", "manual"} else "csv",
                "input_filename": filename or "",
                "input_count": len(rows),
                "line_ids": [
                    fields.Command.create(self._line_values(row, index))
                    for index, row in enumerate(rows, start=1)
                ],
            }
        )
        return self._job_to_dict(job)

    @api.model
    def get_jobs(self, limit=30):
        self._check_access()
        limit = min(max(self._as_int(limit, 30), 1), 100)
        domain = []
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_admin"):
            domain.append(("user_id", "=", self.env.user.id))
        jobs = self.env["lqa.mercadolibre.pricing.job"].search(
            domain,
            order="create_date desc, id desc",
            limit=limit,
        )
        return [self._job_to_dict(job) for job in jobs]

    @api.model
    def get_job(self, job_id):
        self._check_access()
        job = self._get_job(job_id)
        return self._job_to_dict(job, include_lines=True)

    @api.model
    def process_job(self, job_id):
        job = self.env["lqa.mercadolibre.pricing.job"].browse(
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
                    "notified": False,
                }
            )
        return self._job_to_dict(job)

    @api.model
    def get_ready_notifications(self):
        self._check_access()
        jobs = self.env["lqa.mercadolibre.pricing.job"].search(
            [
                ("user_id", "=", self.env.user.id),
                ("state", "in", ["done", "failed"]),
                ("notified", "=", False),
            ],
            order="finished_at desc, id desc",
            limit=5,
        )
        return [self._job_to_dict(job) for job in jobs]

    @api.model
    def mark_jobs_notified(self, job_ids):
        self._check_access()
        ids = [self._as_int(job_id, 0) for job_id in (job_ids or [])]
        jobs = self.env["lqa.mercadolibre.pricing.job"].search(
            [("id", "in", ids), ("user_id", "=", self.env.user.id)]
        )
        jobs.write({"notified": True})
        return True

    @api.model
    def download_job_csv(self, job_id):
        self._check_access()
        job = self._get_job(job_id)
        content = job.result_csv or self._build_result_csv(job)
        if not job.result_csv:
            job.sudo().write({"result_csv": content})
        return {
            "filename": f"{self._csv_safe_name(job.name)}-pricing.csv",
            "content": content,
            "count": job.input_count,
        }

    @api.model
    def download_job_xlsx(self, job_id):
        self._check_access()
        job = self._get_job(job_id)
        content = self._build_result_xlsx(job)
        return {
            "filename": f"{self._csv_safe_name(job.name)}-pricing.xlsx",
            "content": base64.b64encode(content).decode("ascii"),
            "mimetype": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            "count": job.input_count,
        }

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
            items = response.get("items") or []
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
                            "error_message": _("La API no devolvio resultado para esta fila."),
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
                "result_csv": self._build_result_csv(job),
                "finished_at": fields.Datetime.now(),
                "notified": False,
            }
        )

    def _build_result_csv(self, job):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([column[0] for column in self.CSV_OUTPUT_COLUMNS])
        for line in job.line_ids.sorted("sequence"):
            row_source = self._result_row_source(line)
            writer.writerow(
                [
                    self._nested_value(row_source, path)
                    for _, path in self.CSV_OUTPUT_COLUMNS
                ]
            )
        return buffer.getvalue()

    def _build_result_xlsx(self, job):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(
            output,
            {
                "in_memory": True,
                "constant_memory": False,
                "strings_to_formulas": False,
                "strings_to_urls": False,
            },
        )
        worksheet = workbook.add_worksheet("Pricing")
        worksheet.hide_gridlines(2)
        worksheet.freeze_panes(1, 0)

        header_format = workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#2D3277",
                "border": 1,
                "border_color": "#D7DEE7",
                "align": "center",
                "valign": "vcenter",
            }
        )
        text_format = workbook.add_format({"valign": "top"})
        error_format = workbook.add_format(
            {
                "font_color": "#A22B2B",
                "bg_color": "#FFF0F0",
                "text_wrap": True,
                "valign": "top",
            }
        )
        money_format = workbook.add_format(
            {
                "num_format": '$ #,##0.00;[Red]-$ #,##0.00',
                "valign": "top",
            }
        )
        decimal_format = workbook.add_format(
            {
                "num_format": "#,##0.00",
                "valign": "top",
            }
        )
        percentage_format = workbook.add_format(
            {
                "num_format": "0.00%",
                "valign": "top",
            }
        )

        for column_index, (header, _, _, width) in enumerate(
            self.XLSX_OUTPUT_COLUMNS
        ):
            worksheet.write(0, column_index, header, header_format)
            worksheet.set_column(column_index, column_index, width)
        worksheet.set_row(0, 26)

        for row_index, line in enumerate(job.line_ids.sorted("sequence"), start=1):
            row_source = self._result_row_source(line)
            for column_index, (_, path, value_type, _) in enumerate(
                self.XLSX_OUTPUT_COLUMNS
            ):
                value = self._nested_value(row_source, path)
                self._write_xlsx_value(
                    worksheet,
                    row_index,
                    column_index,
                    value,
                    value_type,
                    {
                        "text": text_format,
                        "error": error_format,
                        "money": money_format,
                        "decimal": decimal_format,
                        "percentage": percentage_format,
                    },
                    is_error_column=path == "error",
                )

        last_row = max(len(job.line_ids), 1)
        worksheet.autofilter(
            0,
            0,
            last_row,
            len(self.XLSX_OUTPUT_COLUMNS) - 1,
        )
        worksheet.conditional_format(
            1,
            6,
            last_row,
            6,
            {
                "type": "text",
                "criteria": "containing",
                "value": "Error",
                "format": error_format,
            },
        )
        workbook.close()
        return output.getvalue()

    def _result_row_source(self, line):
        input_payload = self._json_loads(line.input_payload_json)
        response = self._json_loads(line.response_json)
        return {
            "input": input_payload,
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
            numeric_value = self._as_float(value, None)
            if numeric_value is not None:
                worksheet.write_number(
                    row,
                    column,
                    numeric_value,
                    formats[value_type],
                )
                return
        if value_type == "percentage_points":
            numeric_value = self._as_float(value, None)
            if numeric_value is not None:
                worksheet.write_number(
                    row,
                    column,
                    numeric_value / 100,
                    formats["percentage"],
                )
                return
        if value_type == "percentage_decimal":
            numeric_value = self._as_float(value, None)
            if numeric_value is not None:
                worksheet.write_number(
                    row,
                    column,
                    numeric_value,
                    formats["percentage"],
                )
                return
        if value_type == "percentage_text":
            numeric_value = self._percentage_decimal(value)
            if numeric_value is not None:
                worksheet.write_number(
                    row,
                    column,
                    numeric_value,
                    formats["percentage"],
                )
                return
        worksheet.write(
            row,
            column,
            str(value),
            formats["error"] if is_error_column and value else formats["text"],
        )

    def _parse_input(self, content):
        content = str(content or "").strip()
        if not content:
            return []
        if content.startswith("["):
            try:
                data = json.loads(content)
            except ValueError as error:
                raise UserError(_("El JSON ingresado no es valido.")) from error
            return [self._normalize_row(row) for row in data if isinstance(row, dict)]

        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames:
            return [self._normalize_row(row) for row in reader if any(row.values())]

        raise UserError(_("El contenido debe ser CSV con encabezados o un JSON array."))

    def _normalize_row(self, row):
        normalized = {
            "mla": self._clean(self._pick(row, "mla", "MLA")),
            "categoryId": self._clean(
                self._pick(row, "categoryId", "category_id", "categoria", "categoria_id")
            ),
            "publicationType": self._clean(
                self._pick(
                    row,
                    "publicationType",
                    "publication_type",
                    "tipo_publicacion",
                    "listingTypeId",
                )
            ),
            "sku": self._clean(self._pick(row, "sku", "SKU")),
            "salePrice": self._as_float(
                self._pick(row, "salePrice", "sale_price", "precio", "price"),
                None,
            ),
        }
        contribution = self._as_float(
            self._pick(
                row,
                "meliContributionPercentage",
                "meli_contribution_percentage",
                "aporte_meli_porcentaje",
                "contribucion_meli",
            ),
            None,
        )
        if contribution is not None:
            normalized["meliContributionPercentage"] = contribution

        missing = [
            field
            for field in self.REQUIRED_FIELDS
            if normalized.get(field) in (None, "")
        ]
        if missing:
            raise UserError(
                _("Hay filas con campos obligatorios faltantes: %s")
                % ", ".join(missing)
            )
        return normalized

    def _line_values(self, row, index):
        return {
            "sequence": index,
            "mla": row["mla"],
            "category_id": row["categoryId"],
            "publication_type": row["publicationType"],
            "sku": row["sku"],
            "sale_price": row["salePrice"],
            "has_meli_contribution": "meliContributionPercentage" in row,
            "meli_contribution_percentage": row.get("meliContributionPercentage") or 0,
            "input_payload_json": json.dumps(row, ensure_ascii=False, default=str),
        }

    def _pricing_config(self):
        params = self.env["ir.config_parameter"].sudo()
        endpoint = (
            params.get_param("lqa_admin_panel.mercadolibre_pricing_url")
            or os.environ.get("LQA_MERCADOLIBRE_PRICING_URL")
            or self.DEFAULT_ENDPOINT
        )
        api_key = (
            params.get_param("lqa_admin_panel.mercadolibre_pricing_api_key")
            or os.environ.get("LQA_MERCADOLIBRE_PRICING_API_KEY")
        )
        timeout = self._as_int(
            params.get_param("lqa_admin_panel.mercadolibre_pricing_timeout_seconds")
            or os.environ.get("LQA_MERCADOLIBRE_PRICING_TIMEOUT_SECONDS"),
            300,
        )
        if not endpoint or not api_key:
            raise UserError(_("Configura la URL y la API key de Pricing."))
        return endpoint, api_key, timeout

    def _get_job(self, job_id):
        job = self.env["lqa.mercadolibre.pricing.job"].browse(
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
            "canDownload": bool(job.result_csv or job.state in {"done", "failed"}),
        }
        if include_lines:
            data["lines"] = [line.to_panel_dict() for line in job.line_ids]
        return data

    def _job_name(self, source_type, filename):
        if filename:
            return filename
        label = "CSV" if source_type == "csv" else "Manual"
        return f"Pricing {label} {fields.Datetime.now()}"

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(_("No tenes permisos para usar Pricing."))

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
        return "" if current in (None, False) else current

    @staticmethod
    def _json_loads(value):
        if not value:
            return {}
        try:
            return json.loads(value)
        except ValueError:
            return {}

    @staticmethod
    def _as_int(value, default):
        try:
            return int(value)
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
        has_percent_sign = clean_value.endswith("%")
        numeric_value = self._as_float(clean_value.rstrip("%").strip(), None)
        if numeric_value is None:
            return None
        return (
            numeric_value / 100
            if has_percent_sign or abs(numeric_value) > 1
            else numeric_value
        )

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    def _csv_safe_name(self, value):
        clean_value = self._clean(value).lower().replace(" ", "-")
        return "".join(
            character
            for character in clean_value
            if character.isalnum() or character in {"-", "_"}
        ) or "mercadolibre-pricing"
