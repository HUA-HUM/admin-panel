from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    lqa_favorite_menu_ids = fields.Many2many(
        comodel_name="ir.ui.menu",
        relation="lqa_user_menu_favorite_rel",
        column1="user_id",
        column2="menu_id",
        string="Secciones favoritas del panel",
    )
