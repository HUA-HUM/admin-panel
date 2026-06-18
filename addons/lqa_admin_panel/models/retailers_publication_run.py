import json

from odoo import fields, models


class LqaRetailersPublicationRun(models.Model):
    _name = "lqa.retailers.publication.run"
    _description = "Ejecucion de publicacion de retailers"
    _order = "triggered_at desc, id desc"

    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    folder_id = fields.Char(string="Folder ID", required=True, readonly=True)
    marketplaces_json = fields.Text(string="Marketplaces", readonly=True)
    run_id = fields.Char(string="Run ID", index=True, readonly=True)
    status = fields.Char(string="Estado", readonly=True)
    jobs_count = fields.Integer(string="Jobs", readonly=True)
    message = fields.Text(string="Mensaje", readonly=True)
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
            marketplaces = json.loads(self.marketplaces_json or "[]")
        except (TypeError, ValueError):
            marketplaces = []
        normalized_status = (self.status or "").upper()
        return {
            "id": self.id,
            "ok": normalized_status not in {"ERROR", "FAILED"},
            "run_id": self.run_id or "",
            "folder_id": self.folder_id or "",
            "marketplaces": marketplaces if isinstance(marketplaces, list) else [],
            "status": self.status or "",
            "jobs_count": self.jobs_count,
            "message": self.message or "",
            "triggered_at": fields.Datetime.to_string(self.triggered_at),
            "user_name": self.user_id.name or "",
        }
