import csv
import io
import json
import os

from odoo import api, http
from odoo.modules.registry import Registry
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
        [
            "/lqa_admin_panel/accounting/comprobantes/<string:tlqv_code>/pdf",
            "/lqa_admin_panel/accounting/comprobantes/<string:tlqv_code>/cdn",
        ],
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

    @http.route(
        "/lqa_admin_panel/mercadolibre/selections/<int:folder_id>/csv",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def mercadolibre_selection_csv(self, folder_id, columns="", **kwargs):
        service = request.env["lqa.mercadolibre.catalog.service"]
        service._check_access()
        folder = service._get_folder(folder_id)
        column_map = {column[0]: column for column in service.CSV_COLUMNS}
        requested_columns = [
            value.strip()
            for value in str(columns or "").split(",")
            if value.strip() in column_map
        ]
        if not requested_columns:
            requested_columns = list(service.DEFAULT_CSV_COLUMNS)

        filename = (
            f"{service._csv_safe_name(folder.name)}-mercadolibre.csv"
        )
        dbname = request.env.cr.dbname
        uid = request.env.user.id
        context = dict(request.env.context)

        def stream_csv():
            header_buffer = io.StringIO(newline="")
            header_writer = csv.writer(header_buffer)
            header_writer.writerow(
                [column_map[key][1] for key in requested_columns]
            )
            yield ("\ufeff" + header_buffer.getvalue()).encode("utf-8")

            last_id = 0
            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, uid, context)
                export_service = env["lqa.mercadolibre.catalog.service"]
                line_model = env["lqa.mercadolibre.selection.item"]
                while True:
                    lines = line_model.search(
                        [
                            ("folder_id", "=", folder_id),
                            ("id", ">", last_id),
                        ],
                        order="id",
                        limit=5000,
                    )
                    if not lines:
                        break
                    batch_buffer = io.StringIO(newline="")
                    writer = csv.writer(batch_buffer)
                    for line in lines:
                        writer.writerow(
                            [
                                export_service._csv_line_value(
                                    line,
                                    column_map[key],
                                )
                                for key in requested_columns
                            ]
                        )
                    last_id = lines[-1].id
                    yield batch_buffer.getvalue().encode("utf-8")
                    env.invalidate_all()

        response = request.make_response(
            stream_csv(),
            headers=[
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition", http.content_disposition(filename)),
                ("X-Accel-Buffering", "no"),
                ("Cache-Control", "no-store"),
            ],
        )
        response.direct_passthrough = True
        return response

    @http.route(
        "/lqa_admin_panel/mercadolibre/pricing/imports/<int:import_id>/xlsx",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def mercadolibre_pricing_import_xlsx(self, import_id, **kwargs):
        service = request.env["lqa.mercadolibre.pricing.service"]
        service._check_access()
        import_job = service._get_folder_import(import_id)
        path = import_job.export_path or ""
        if import_job.export_state != "done" or not os.path.isfile(path):
            return request.not_found()

        filename = (
            f"{service._csv_safe_name(import_job.folder_id.name)}-pricing.xlsx"
        )

        def stream_xlsx():
            with open(path, "rb") as export_file:
                while True:
                    chunk = export_file.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk

        response = request.make_response(
            stream_xlsx(),
            headers=[
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet",
                ),
                ("Content-Disposition", http.content_disposition(filename)),
                ("Content-Length", str(os.path.getsize(path))),
                ("X-Accel-Buffering", "no"),
                ("Cache-Control", "no-store"),
            ],
        )
        response.direct_passthrough = True
        return response
