import json

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

    @http.route(
        "/lqa_admin_panel/manifest.webmanifest",
        type="http",
        auth="public",
        csrf=False,
        sitemap=False,
    )
    def webmanifest(self):
        icon = "/lqa_admin_panel/static/src/img/tienda-logo-app.png?v=4"
        manifest = {
            "name": "Tienda Lo Quiero Aca - Panel Comercial",
            "short_name": "TLQ Panel",
            "description": "Panel comercial interno de Tienda Lo Quiero Aca.",
            "start_url": "/odoo",
            "scope": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#ff4f5a",
            "icons": [
                {
                    "src": icon,
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
                {
                    "src": icon,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
        }
        return request.make_response(
            json.dumps(manifest),
            headers=[("Content-Type", "application/manifest+json")],
        )

    @http.route(
        "/lqa_admin_panel/accounting/comprobantes/<string:tlqv_code>/pdf",
        type="http",
        auth="user",
        csrf=False,
        sitemap=False,
    )
    def accounting_comprobante_pdf(self, tlqv_code, **kwargs):
        result = request.env["lqa.accounting.service"].create_tlqv_document_cdn(
            tlqv_code
        )
        return request.redirect(result["cdnUrl"], code=303)
