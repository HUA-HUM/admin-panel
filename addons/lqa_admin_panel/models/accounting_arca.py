import csv
import io
import json
import os
import re
from urllib.parse import quote

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaAccountingTlqvClientJob(models.Model):
    _name = "lqa.accounting.tlqv.client.job"
    _description = "Lote de creacion de clientes TLQV"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, readonly=True, default="Clientes TLQV")
    user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    state = fields.Selection(
        selection=[
            ("processing", "Procesando"),
            ("done", "Listo"),
            ("partial", "Parcial"),
            ("failed", "Fallido"),
        ],
        default="processing",
        required=True,
        readonly=True,
        index=True,
    )
    source_filename = fields.Char(readonly=True)
    input_count = fields.Integer(readonly=True)
    success_count = fields.Integer(readonly=True)
    failed_count = fields.Integer(readonly=True)
    issue_count = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    line_ids = fields.One2many(
        "lqa.accounting.tlqv.client.line",
        "job_id",
        readonly=True,
    )


class LqaAccountingTlqvClientLine(models.Model):
    _name = "lqa.accounting.tlqv.client.line"
    _description = "Resultado de creacion de cliente TLQV"
    _order = "sequence asc, id asc"

    job_id = fields.Many2one(
        "lqa.accounting.tlqv.client.job",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    tlqv_code = fields.Char(required=True, index=True)
    state = fields.Selection(
        selection=[
            ("success", "Creado"),
            ("issue", "Con issue"),
            ("failed", "Fallido"),
        ],
        required=True,
        default="failed",
        readonly=True,
        index=True,
    )
    http_status = fields.Integer(readonly=True)
    response_status = fields.Char(readonly=True)
    can_continue = fields.Boolean(readonly=True)
    message = fields.Text(readonly=True)
    issues_count = fields.Integer(readonly=True)
    response_payload = fields.Text(readonly=True)
    issues_payload = fields.Text(readonly=True)
    processed_at = fields.Datetime(readonly=True)


class LqaAccountingService(models.AbstractModel):
    _name = "lqa.accounting.service"
    _description = "Servicio contable ARCA"

    DEFAULT_INVOICE_API_URL = "https://invoice.loquieroaca.com"
    DEFAULT_MADRE_API_URL = "https://api.madre.loquieroaca.com"
    DEFAULT_TIMEOUT_SECONDS = 120
    MAX_TLQV_CODES = 2000
    TLQV_PATTERN = re.compile(r"TLQV[-\s]?(\d+)", re.IGNORECASE)
    HEADER_ALIASES = {
        "tlqv",
        "tlqvcode",
        "tlqv_code",
        "codigo",
        "codigo_tlqv",
        "orden",
        "order",
        "numero_orden",
        "numeroorden",
        "codigotlqv",
    }

    @api.model
    def create_clients_from_tlqv_csv(self, content="", filename="", manual_input=""):
        self._check_access()
        source = "\n".join(
            value for value in (content or "", manual_input or "") if value
        )
        tlqv_codes = self._parse_tlqv_codes(source)
        if not tlqv_codes:
            raise UserError(_("No encontre codigos TLQV validos para procesar."))
        if len(tlqv_codes) > self.MAX_TLQV_CODES:
            raise UserError(
                _("Podes procesar hasta %s codigos TLQV por lote.")
                % self.MAX_TLQV_CODES
            )

        job = self.env["lqa.accounting.tlqv.client.job"].sudo().create(
            {
                "name": self._job_name(filename, len(tlqv_codes)),
                "user_id": self.env.user.id,
                "source_filename": self._clean(filename),
                "input_count": len(tlqv_codes),
                "started_at": fields.Datetime.now(),
            }
        )

        try:
            for sequence, tlqv_code in enumerate(tlqv_codes, start=1):
                result = self._create_client_from_tlqv(tlqv_code)
                result["sequence"] = sequence
                result["job_id"] = job.id
                self.env["lqa.accounting.tlqv.client.line"].sudo().create(result)
        except Exception as error:
            job.write(
                {
                    "state": "failed",
                    "error_message": str(error),
                    "finished_at": fields.Datetime.now(),
                }
            )
            raise

        self._finalize_job(job)
        return self._job_to_dict(job, include_lines=True)

    @api.model
    def get_tlqv_client_jobs(self, limit=30):
        self._check_access()
        limit = min(max(self._as_int(limit, 30), 1), 100)
        domain = []
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_admin"):
            domain.append(("user_id", "=", self.env.user.id))
        jobs = self.env["lqa.accounting.tlqv.client.job"].search(
            domain,
            order="create_date desc, id desc",
            limit=limit,
        )
        return [self._job_to_dict(job, include_lines=True) for job in jobs]

    @api.model
    def get_xubio_comprobantes(self, filters=None):
        self._check_access()
        filters = filters or {}
        limit = min(max(self._as_int(filters.get("limit"), 50), 1), 200)
        offset = max(self._as_int(filters.get("offset"), 0), 0)
        params = {"limit": limit, "offset": offset}
        for key in (
            "tlqvCode",
            "numeroDocumento",
            "clienteCodigo",
            "mlOrderId",
            "documentKind",
            "fechaDesde",
            "fechaHasta",
        ):
            value = self._clean(filters.get(key))
            if value:
                params[key] = value

        response = self._request_json(
            "GET",
            self._join_url(
                self._madre_base_url(),
                "/api/internal/xubio/comprobantes",
            ),
            params=params,
            headers=self._madre_headers(),
            timeout=self._timeout(),
        )
        payload = response["payload"] if isinstance(response["payload"], dict) else {}
        items = self._response_items(payload)
        total = self._as_int(
            payload.get("total")
            or payload.get("count")
            or payload.get("totalCount"),
            len(items),
        )
        return {
            "items": [self._normalize_comprobante(item) for item in items],
            "pagination": {
                "total": total,
                "count": len(items),
                "limit": limit,
                "offset": offset,
                "page": (offset // limit) + 1,
                "has_previous": offset > 0,
                "has_next": offset + limit < total,
                "next_offset": offset + limit,
            },
            "raw": payload,
        }

    def _create_client_from_tlqv(self, tlqv_code):
        invoice_response = self._request_json(
            "POST",
            self._join_url(
                self._invoice_base_url(),
                "/internal/tlqv-invoice/clientes/create-from-tlqv",
            ),
            payload={"tlqvCode": tlqv_code},
            headers=self._invoice_headers(),
            timeout=self._timeout(),
        )
        payload = invoice_response["payload"]
        payload_dict = payload if isinstance(payload, dict) else {}
        success = invoice_response["ok"] and self._is_success_payload(payload_dict)
        issues_payload = {}
        issues_count = 0
        if not success:
            issues_response = self._fetch_client_issues(tlqv_code)
            issues_payload = issues_response.get("payload") or {}
            issues_count = len(self._response_items(issues_payload))

        state = "success" if success else "issue" if issues_count else "failed"
        return {
            "tlqv_code": tlqv_code,
            "state": state,
            "http_status": invoice_response["status_code"],
            "response_status": self._clean(payload_dict.get("status")),
            "can_continue": bool(payload_dict.get("canContinue")),
            "message": self._extract_message(payload_dict, issues_payload),
            "issues_count": issues_count,
            "response_payload": self._json_dumps(payload),
            "issues_payload": self._json_dumps(issues_payload),
            "processed_at": fields.Datetime.now(),
        }

    def _fetch_client_issues(self, tlqv_code):
        try:
            return self._request_json(
                "GET",
                self._join_url(
                    self._madre_base_url(),
                    (
                        "/api/internal/invoice/client-issues/by-tlqv-code/"
                        f"{quote(tlqv_code, safe='')}"
                    ),
                ),
                headers=self._madre_headers(),
                timeout=self._timeout(),
            )
        except UserError as error:
            return {
                "ok": False,
                "status_code": 0,
                "payload": {"error": str(error)},
                "text": str(error),
            }

    def _request_json(
        self,
        method,
        url,
        payload=None,
        params=None,
        headers=None,
        timeout=None,
    ):
        request_headers = {"Accept": "application/json"}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=request_headers,
                json=payload,
                params=params,
                timeout=timeout or self._timeout(),
            )
        except requests.RequestException as error:
            raise UserError(_("No se pudo conectar con la API interna: %s") % error)

        response_text = response.text or ""
        try:
            response_payload = response.json() if response_text else {}
        except ValueError:
            response_payload = {"raw": response_text}
        return {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "payload": response_payload,
            "text": response_text,
        }

    def _finalize_job(self, job):
        lines = job.line_ids
        success_count = len(lines.filtered(lambda line: line.state == "success"))
        issue_count = len(lines.filtered(lambda line: line.state == "issue"))
        failed_count = len(lines.filtered(lambda line: line.state == "failed"))
        if not lines or (failed_count and not success_count and not issue_count):
            state = "failed"
        elif issue_count or failed_count:
            state = "partial"
        else:
            state = "done"
        job.write(
            {
                "state": state,
                "success_count": success_count,
                "issue_count": issue_count,
                "failed_count": failed_count,
                "finished_at": fields.Datetime.now(),
            }
        )

    def _parse_tlqv_codes(self, content):
        content = (content or "").replace("\ufeff", "").strip()
        if not content:
            return []
        rows = self._csv_rows(content)
        if not rows:
            return []
        header_index = self._header_index(rows[0])
        candidates = []
        data_rows = rows[1:] if header_index is not None else rows
        for row in data_rows:
            cells = row if header_index is None else [row[header_index] if len(row) > header_index else ""]
            for cell in cells:
                code = self._normalize_tlqv(cell)
                if code:
                    candidates.append(code)
        return list(dict.fromkeys(candidates))

    def _csv_rows(self, content):
        sample = content[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(content), dialect)
        return [
            [self._clean(cell) for cell in row]
            for row in reader
            if any(self._clean(cell) for cell in row)
        ]

    def _header_index(self, row):
        for index, value in enumerate(row):
            normalized = re.sub(r"[^a-z0-9_]+", "", value.lower().strip())
            if normalized in self.HEADER_ALIASES:
                return index
        return None

    def _normalize_tlqv(self, value):
        value = self._clean(value)
        if not value:
            return ""
        match = self.TLQV_PATTERN.search(value)
        if match:
            return f"TLQV-{match.group(1)}"
        if value.isdigit():
            return f"TLQV-{value}"
        return ""

    def _is_success_payload(self, payload):
        if not isinstance(payload, dict):
            return True
        if payload.get("canContinue") is False:
            return False
        status = self._clean(payload.get("status")).lower()
        if status in {
            "invalid_fiscal_document",
            "error",
            "failed",
            "failure",
            "blocked",
        }:
            return False
        return True

    def _extract_message(self, response_payload, issues_payload):
        issue_items = self._response_items(issues_payload)
        if issue_items:
            first_issue = issue_items[0]
            if isinstance(first_issue, dict):
                return self._clean(
                    first_issue.get("message")
                    or ", ".join(first_issue.get("messages") or [])
                    or first_issue.get("reason")
                )
        if isinstance(response_payload, dict):
            return self._clean(
                response_payload.get("message")
                or response_payload.get("error")
                or response_payload.get("status")
            )
        return ""

    def _normalize_comprobante(self, item):
        item = item if isinstance(item, dict) else {}
        product_items = item.get("productItems")
        if not isinstance(product_items, list):
            raw_detail = item.get("rawDetailPayload")
            product_items = (
                raw_detail.get("transaccionProductoItems")
                if isinstance(raw_detail, dict)
                and isinstance(raw_detail.get("transaccionProductoItems"), list)
                else []
            )
        return {
            "id": item.get("id"),
            "xubioTransactionId": item.get("xubioTransactionId"),
            "numeroDocumento": self._clean(item.get("numeroDocumento")),
            "documentKind": self._clean(item.get("documentKind")),
            "tipoNombre": self._clean(item.get("tipoNombre")),
            "letraComprobante": self._clean(item.get("letraComprobante")),
            "descripcion": self._clean(item.get("descripcion")),
            "tlqvCode": self._clean(item.get("tlqvCode")),
            "mlOrderId": self._clean(item.get("mlOrderId")),
            "clienteCodigo": self._clean(item.get("clienteCodigo")),
            "clienteNombre": self._clean(item.get("clienteNombre")),
            "fechaEmision": self._clean(item.get("fechaEmision")),
            "importeGravado": item.get("importeGravado"),
            "importeImpuestos": item.get("importeImpuestos"),
            "importeTotal": item.get("importeTotal"),
            "monedaCodigo": self._clean(item.get("monedaCodigo")),
            "cae": self._clean(item.get("cae")),
            "fiscalmenteEmitido": bool(item.get("fiscalmenteEmitido")),
            "syncedAt": self._clean(item.get("syncedAt")),
            "productItemsCount": len(product_items),
        }

    def _job_to_dict(self, job, include_lines=False):
        data = {
            "id": job.id,
            "name": job.name,
            "state": job.state,
            "user": job.user_id.name,
            "sourceFilename": job.source_filename or "",
            "inputCount": job.input_count,
            "successCount": job.success_count,
            "failedCount": job.failed_count,
            "issueCount": job.issue_count,
            "errorMessage": job.error_message or "",
            "createdAt": fields.Datetime.to_string(job.create_date),
            "startedAt": fields.Datetime.to_string(job.started_at) if job.started_at else "",
            "finishedAt": fields.Datetime.to_string(job.finished_at) if job.finished_at else "",
        }
        if include_lines:
            data["lines"] = [self._line_to_dict(line) for line in job.line_ids]
        return data

    def _line_to_dict(self, line):
        return {
            "id": line.id,
            "tlqvCode": line.tlqv_code,
            "state": line.state,
            "httpStatus": line.http_status,
            "responseStatus": line.response_status or "",
            "canContinue": bool(line.can_continue),
            "message": line.message or "",
            "issuesCount": line.issues_count,
            "processedAt": fields.Datetime.to_string(line.processed_at) if line.processed_at else "",
        }

    def _response_items(self, payload):
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return items
            data = payload.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"]
            if isinstance(payload.get("list"), list):
                return payload["list"]
        if isinstance(payload, list):
            return payload
        return []

    def _invoice_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param("lqa_admin_panel.accounting_invoice_api_url", "")
            or os.environ.get("LQA_ACCOUNTING_INVOICE_API_URL")
            or self.DEFAULT_INVOICE_API_URL
        ).strip()

    def _madre_base_url(self):
        params = self.env["ir.config_parameter"].sudo()
        return (
            params.get_param("lqa_admin_panel.accounting_madre_api_url", "")
            or os.environ.get("LQA_ACCOUNTING_MADRE_API_URL")
            or self.DEFAULT_MADRE_API_URL
        ).strip()

    def _invoice_headers(self):
        key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("lqa_admin_panel.accounting_invoice_api_key", "")
            or os.environ.get("LQA_ACCOUNTING_INVOICE_API_KEY", "")
        ).strip()
        if not key:
            raise UserError(_("Configura la clave interna de Invoice ARCA."))
        return {"x-internal-api-key": key}

    def _madre_headers(self):
        key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("lqa_admin_panel.accounting_madre_api_key", "")
            or os.environ.get("LQA_ACCOUNTING_MADRE_API_KEY", "")
            or os.environ.get("LQA_INTERNAL_API_KEY", "")
        ).strip()
        if not key:
            raise UserError(_("Configura la clave interna de Madre para contabilidad."))
        return {"x-internal-api-key": key}

    def _timeout(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "lqa_admin_panel.accounting_timeout_seconds",
                self.DEFAULT_TIMEOUT_SECONDS,
            )
        )
        return min(max(self._as_int(value, self.DEFAULT_TIMEOUT_SECONDS), 20), 300)

    def _check_access(self):
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_commercial_user"):
            raise AccessError(_("No tenes permisos para acceder al modulo contable."))

    def _job_name(self, filename, count):
        filename = self._clean(filename)
        if filename:
            return _("Clientes TLQV - %s") % filename
        return _("Clientes TLQV - %s codigos") % count

    @staticmethod
    def _json_dumps(value):
        return json.dumps(value or {}, ensure_ascii=False, default=str)

    @staticmethod
    def _join_url(base_url, path):
        return "/".join(
            [
                str(base_url or "").rstrip("/"),
                str(path or "").lstrip("/"),
            ]
        )

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    @staticmethod
    def _as_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
