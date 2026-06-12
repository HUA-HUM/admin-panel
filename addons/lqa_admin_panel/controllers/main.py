from odoo import http
from odoo.http import request


class LqaAdminPanelController(http.Controller):
    @http.route("/lqa_admin_panel/health", type="json", auth="user")
    def health(self):
        return {
            "ok": True,
            "module": "lqa_admin_panel",
            "environment": request.env["ir.config_parameter"].sudo().get_param(
                "lqa_admin_panel.api_environment", "development"
            ),
        }
