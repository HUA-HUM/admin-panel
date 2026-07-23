import json

from odoo import fields, models


class LqaRetailersBulkActionRun(models.Model):
    _name = "lqa.retailers.bulk.action.run"
    _description = "Registro de acciones masivas de retailers"
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
            ("published", "Publicaciones publicadas"),
            ("sku", "SKU puntual"),
            ("bulk", "Archivo de SKUs"),
        ],
        string="Accion",
        required=True,
        readonly=True,
        index=True,
    )
    marketplace = fields.Char(string="Marketplace", required=True, readonly=True, index=True)
    marketplace_name = fields.Char(string="Marketplace visible", readonly=True)
    sku = fields.Char(string="SKU", readonly=True)
    sku_count = fields.Integer(string="Cantidad de SKUs", readonly=True)
    filename = fields.Char(string="Archivo", readonly=True)
    run_id = fields.Char(string="Run ID", readonly=True, index=True)
    job_id = fields.Char(string="Job API", readonly=True)
    status = fields.Char(string="Estado", readonly=True, index=True)
    message = fields.Text(string="Mensaje", readonly=True)
    note = fields.Text(string="Nota", readonly=True)
    response_json = fields.Text(string="Respuesta API", readonly=True)
    triggered_at = fields.Datetime(
        string="Ejecutado",
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )

    def to_panel_dict(self):
        self.ensure_one()
        try:
            response = json.loads(self.response_json or "{}")
        except (TypeError, ValueError):
            response = {}
        return {
            "id": self.id,
            "action_type": self.action_type or "",
            "marketplace": self.marketplace or "",
            "marketplace_name": self.marketplace_name or "",
            "sku": self.sku or "",
            "sku_count": self.sku_count,
            "filename": self.filename or "",
            "run_id": self.run_id or "",
            "job_id": self.job_id or "",
            "status": self.status or "",
            "message": self.message or "",
            "note": self.note or "",
            "triggered_at": fields.Datetime.to_string(self.triggered_at),
            "user_name": self.user_id.name or "",
            "response": response if isinstance(response, dict) else {},
        }
