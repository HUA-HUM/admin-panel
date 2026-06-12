from odoo import api, models


class LqaDashboardService(models.AbstractModel):
    _name = "lqa.dashboard.service"
    _description = "Servicio para dashboards del panel comercial"

    @api.model
    def get_dashboard_state(self, selected_module_code=False):
        params = self.env["ir.config_parameter"].sudo()
        domain = [("active", "=", True)]
        if selected_module_code:
            domain.append(("code", "=", selected_module_code))

        modules = self.env["lqa.panel.module"].search(domain, order="sequence, name")
        all_modules = self.env["lqa.panel.module"].search(
            [("active", "=", True)], order="sequence, name"
        )

        return {
            "environment": params.get_param(
                "lqa_admin_panel.api_environment", "development"
            ),
            "api_configured": bool(params.get_param("lqa_admin_panel.api_base_url")),
            "selected_module_code": selected_module_code or False,
            "modules": [self._serialize_module(module) for module in modules],
            "navigation_modules": [
                self._serialize_module(module, include_sections=False)
                for module in all_modules
            ],
        }

    def _serialize_module(self, module, include_sections=True):
        action_id = self._action_id_from_xmlid(module.dashboard_action_xmlid)
        data = {
            "id": module.id,
            "name": module.name,
            "code": module.code,
            "description": module.description or "",
            "sequence": module.sequence,
            "action_id": action_id,
            "metrics": self._module_metrics(module.code),
        }
        if include_sections:
            data["sections"] = [
                {
                    "id": section.id,
                    "name": section.name,
                    "code": section.code,
                    "description": section.description or "",
                    "badge": section.badge or "",
                    "status": section.status,
                    "action_id": self._action_id_from_xmlid(section.action_xmlid),
                }
                for section in module.section_ids.filtered("active").sorted("sequence")
            ]
        return data

    def _module_metrics(self, code):
        if code == "automeli":
            catalog_model = self.env["lqa.automeli.catalog.item"].sudo()
            return [
                {
                    "label": "Items catalogo",
                    "value": catalog_model.search_count([("active", "=", True)]),
                },
                {
                    "label": "Listos",
                    "value": catalog_model.search_count([("status", "=", "ready")]),
                },
                {
                    "label": "Con error",
                    "value": catalog_model.search_count([("status", "=", "error")]),
                },
            ]
        if code == "mercadolibre":
            return [
                {"label": "Seccion", "value": "Catalogo"},
                {"label": "API", "value": "Conectada"},
            ]
        return []

    def _action_id_from_xmlid(self, xmlid):
        if not xmlid:
            return False
        action = self.env.ref(xmlid, raise_if_not_found=False)
        return action.id if action else False
