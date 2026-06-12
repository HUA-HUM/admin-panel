from odoo import fields, models


class LqaPanelModule(models.Model):
    _name = "lqa.panel.module"
    _description = "Modulo del panel comercial"
    _order = "sequence, name"

    name = fields.Char(string="Modulo", required=True)
    code = fields.Char(string="Codigo", required=True, index=True)
    description = fields.Text(string="Descripcion")
    sequence = fields.Integer(default=10)
    dashboard_action_xmlid = fields.Char(string="Accion dashboard")
    section_ids = fields.One2many(
        comodel_name="lqa.panel.section",
        inverse_name="module_id",
        string="Secciones",
    )
    active = fields.Boolean(default=True)


class LqaPanelSection(models.Model):
    _name = "lqa.panel.section"
    _description = "Seccion del panel comercial"
    _order = "module_id, sequence, name"

    name = fields.Char(string="Seccion", required=True)
    code = fields.Char(string="Codigo", required=True, index=True)
    module_id = fields.Many2one(
        comodel_name="lqa.panel.module",
        string="Modulo",
        required=True,
        ondelete="cascade",
    )
    description = fields.Text(string="Descripcion")
    badge = fields.Char(string="Etiqueta")
    status = fields.Selection(
        selection=[
            ("available", "Disponible"),
            ("planned", "Planificada"),
            ("blocked", "Bloqueada"),
        ],
        default="available",
        required=True,
    )
    sequence = fields.Integer(default=10)
    action_xmlid = fields.Char(string="Accion")
    active = fields.Boolean(default=True)
