import json
import os
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class LqaMercadolibreDeletionBatch(models.Model):
    _name = "lqa.mercadolibre.deletion.batch"
    _description = "Lote de eliminacion MercadoLibre"
    _order = "create_date desc, id desc"

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Usuario",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    app_key = fields.Char(string="App key", required=True, default="default")
    reason = fields.Text(string="Motivo", readonly=True)
    status = fields.Selection(
        selection=[
            ("processing", "Procesando"),
            ("completed", "Completado"),
            ("partial", "Parcial"),
            ("failed", "Fallido"),
        ],
        required=True,
        default="processing",
        readonly=True,
    )
    requested_count = fields.Integer(string="Solicitados", readonly=True)
    deleted_count = fields.Integer(string="Eliminados", readonly=True)
    failed_count = fields.Integer(string="Fallidos", readonly=True)
    response_payload = fields.Text(string="Respuesta API", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)
    line_ids = fields.One2many(
        comodel_name="lqa.mercadolibre.deletion.line",
        inverse_name="batch_id",
        string="Publicaciones",
        readonly=True,
    )


class LqaMercadolibreDeletionLine(models.Model):
    _name = "lqa.mercadolibre.deletion.line"
    _description = "Publicacion eliminada de MercadoLibre"
    _order = "id"

    batch_id = fields.Many2one(
        comodel_name="lqa.mercadolibre.deletion.batch",
        string="Lote",
        required=True,
        ondelete="cascade",
        index=True,
    )
    mla = fields.Char(string="MLA", required=True, index=True)
    status = fields.Selection(
        selection=[
            ("processing", "Procesando"),
            ("deleted", "Eliminado"),
            ("failed", "Fallido"),
        ],
        required=True,
        default="processing",
        readonly=True,
    )
    message = fields.Char(string="Detalle", readonly=True)


class LqaMercadolibreDeletionService(models.AbstractModel):
    _name = "lqa.mercadolibre.deletion.service"
    _description = "Servicio de eliminacion MercadoLibre"

    DEFAULT_ENDPOINT = (
        "https://api.meli.loquieroaca.com/meli/products/bulk/delete"
    )
    DEFAULT_CHUNK_SIZE = 1000
    MLA_PATTERN = re.compile(r"^MLA\d+$")

    @api.model
    def delete_products(self, ids=None, app_key="default", reason=""):
        self._check_access()
        normalized_ids = self._normalize_ids(ids or [])
        if not normalized_ids:
            raise UserError(_("Ingresa al menos una publicacion MLA valida."))

        app_key = (app_key or "default").strip() or "default"
        reason = self._clean(reason)
        batch = self.env["lqa.mercadolibre.deletion.batch"].sudo().create(
            {
                "user_id": self.env.user.id,
                "app_key": app_key,
                "reason": reason,
                "requested_count": len(normalized_ids),
                "line_ids": [
                    fields.Command.create({"mla": mla})
                    for mla in normalized_ids
                ],
            }
        )

        params = self.env["ir.config_parameter"].sudo()
        endpoint = params.get_param(
            "lqa_admin_panel.mercadolibre_delete_url",
            self.DEFAULT_ENDPOINT,
        ) or os.environ.get("LQA_MERCADOLIBRE_DELETE_URL", self.DEFAULT_ENDPOINT)
        api_key = (
            params.get_param("lqa_admin_panel.mercadolibre_delete_api_key")
            or os.environ.get("LQA_MERCADOLIBRE_DELETE_API_KEY")
        )
        if not endpoint or not api_key:
            return self._mark_failed(
                batch,
                _("Configura la URL y la clave interna del eliminador."),
            )

        chunk_size = self._delete_chunk_size(params)
        responses = []
        failed = {}
        for offset in range(0, len(normalized_ids), chunk_size):
            chunk = normalized_ids[offset : offset + chunk_size]
            try:
                response = self.env["lqa.api.client"].request_absolute_json(
                    "POST",
                    endpoint,
                    payload={"ids": chunk, "appKey": app_key},
                    headers={"x-internal-api-key": api_key},
                )
                chunk_failed = self._extract_failed_ids(response)
                failed.update(chunk_failed)
                responses.append(
                    {
                        "offset": offset,
                        "count": len(chunk),
                        "failed_count": len(chunk_failed),
                        "response": response,
                    }
                )
            except UserError as error:
                message = str(error)
                for mla in chunk:
                    failed[mla] = message
                responses.append(
                    {
                        "offset": offset,
                        "count": len(chunk),
                        "failed_count": len(chunk),
                        "error": message,
                    }
                )

        deleted_count = 0
        failed_count = 0
        for line in batch.line_ids:
            failure = failed.get(line.mla)
            if failure:
                failed_count += 1
                line.write({"status": "failed", "message": failure})
            else:
                deleted_count += 1
                line.write({"status": "deleted"})

        batch.write(
            {
                "status": (
                    "failed"
                    if failed_count == batch.requested_count
                    else "partial"
                    if failed_count
                    else "completed"
                ),
                "deleted_count": deleted_count,
                "failed_count": failed_count,
                "response_payload": json.dumps(
                    {
                        "chunk_size": chunk_size,
                        "chunks": responses,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            }
        )
        return {
            "ok": not failed_count,
            "batch_id": batch.id,
            "deleted_count": deleted_count,
            "failed_count": failed_count,
            "message": (
                _("El lote se proceso correctamente.")
                if not failed_count
                else _("No se pudo procesar ningun bloque del lote.")
                if failed_count == batch.requested_count
                else _("El lote termino con algunas publicaciones fallidas.")
            ),
        }

    @api.model
    def get_history(self, limit=50):
        self._check_access()
        limit = min(max(self._as_int(limit, 50), 1), 200)
        batches = self.env["lqa.mercadolibre.deletion.batch"].search(
            [],
            order="create_date desc, id desc",
            limit=limit,
        )
        return [
            {
                "id": batch.id,
                "date": fields.Datetime.to_string(batch.create_date),
                "user": batch.user_id.name,
                "app_key": batch.app_key,
                "reason": batch.reason or "",
                "status": batch.status,
                "requested_count": batch.requested_count,
                "deleted_count": batch.deleted_count,
                "failed_count": batch.failed_count,
                "error_message": batch.error_message or "",
                "lines": [
                    {
                        "id": line.id,
                        "mla": line.mla,
                        "status": line.status,
                        "message": line.message or "",
                    }
                    for line in batch.line_ids
                ],
            }
            for batch in batches
        ]

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(_("No tenes permisos para eliminar publicaciones."))

    def _normalize_ids(self, ids):
        normalized = []
        seen = set()
        for raw_id in ids:
            mla = str(raw_id or "").strip().upper()
            if not self.MLA_PATTERN.fullmatch(mla) or mla in seen:
                continue
            seen.add(mla)
            normalized.append(mla)
        return normalized

    def _delete_chunk_size(self, params):
        value = (
            params.get_param("lqa_admin_panel.mercadolibre_delete_chunk_size")
            or os.environ.get("LQA_MERCADOLIBRE_DELETE_CHUNK_SIZE")
            or self.DEFAULT_CHUNK_SIZE
        )
        return min(max(self._as_int(value, self.DEFAULT_CHUNK_SIZE), 1), 1000)

    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    def _mark_failed(self, batch, message):
        batch.line_ids.write({"status": "failed", "message": message})
        batch.write(
            {
                "status": "failed",
                "failed_count": batch.requested_count,
                "error_message": message,
            }
        )
        return {
            "ok": False,
            "batch_id": batch.id,
            "deleted_count": 0,
            "failed_count": batch.requested_count,
            "message": message,
        }

    @staticmethod
    def _extract_failed_ids(response):
        failed = {}
        raw_failed = response.get("failed") if isinstance(response, dict) else None
        if isinstance(raw_failed, list):
            for item in raw_failed:
                if isinstance(item, str):
                    failed[item.upper()] = _("La API informo un error.")
                elif isinstance(item, dict):
                    mla = str(item.get("id") or item.get("mla") or "").upper()
                    if mla:
                        failed[mla] = str(
                            item.get("message") or item.get("error") or "Error"
                        )

        results = response.get("results") if isinstance(response, dict) else None
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "").lower()
                if status not in {"failed", "error"}:
                    continue
                mla = str(item.get("id") or item.get("mla") or "").upper()
                if mla:
                    failed[mla] = str(
                        item.get("message") or item.get("error") or "Error"
                    )
        return failed

    @staticmethod
    def _as_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
