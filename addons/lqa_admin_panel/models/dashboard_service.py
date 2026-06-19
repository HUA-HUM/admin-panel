import json

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class LqaDashboardService(models.AbstractModel):
    _name = "lqa.dashboard.service"
    _description = "Servicio para dashboards del panel comercial"

    @api.model
    def get_dashboard_state(self, selected_module_code=False):
        self._check_access()
        domain = [("active", "=", True)]
        if selected_module_code:
            domain.append(("code", "=", selected_module_code))

        modules = self.env["lqa.panel.module"].search(domain, order="sequence, name")
        return {
            "selected_module_code": selected_module_code or False,
            "modules": [self._serialize_module(module) for module in modules],
            "favorites": self._serialize_favorite_menus(),
        }

    @api.model
    def get_menu_favorites_state(self):
        self._check_access()
        return self._favorite_state()

    @api.model
    def toggle_menu_favorite(self, menu_id):
        self._check_access()
        menu = self.env["ir.ui.menu"].browse(self._as_int(menu_id)).exists()
        visible_menu_ids = self.env["ir.ui.menu"]._visible_menu_ids()
        if (
            not menu
            or menu.id not in visible_menu_ids
            or not menu.action
            or not self._is_panel_menu(menu)
        ):
            raise UserError(_("La seccion seleccionada no se puede agregar a favoritos."))

        favorite_menu_ids = self._favorite_menu_ids()
        if menu.id in favorite_menu_ids:
            favorite_menu_ids.remove(menu.id)
        else:
            favorite_menu_ids.append(menu.id)
        self._write_favorite_menu_ids(favorite_menu_ids)
        return self._favorite_state()

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
        if code == "retailers":
            return [
                {"label": "Marketplaces", "value": 4},
                {"label": "Orders", "value": "24/48/72h"},
                {"label": "Imports", "value": "Manual"},
            ]
        return []

    def _action_id_from_xmlid(self, xmlid):
        if not xmlid:
            return False
        action = self.env.ref(xmlid, raise_if_not_found=False)
        return action.id if action else False

    def _favorite_state(self):
        menus = self._favorite_menus()
        root = self.env.ref("lqa_admin_panel.menu_lqa_root", raise_if_not_found=False)
        return {
            "panel_root_menu_id": root.id if root else False,
            "favorite_menu_ids": menus.ids,
            "favorites": [
                self._serialize_favorite_menu(menu)
                for menu in menus
            ],
        }

    def _favorite_menus(self):
        visible_menu_ids = self.env["ir.ui.menu"]._visible_menu_ids()
        menus = self.env["ir.ui.menu"].browse(self._favorite_menu_ids()).exists().filtered(
            lambda menu: (
                menu.id in visible_menu_ids
                and menu.active
                and menu.action
                and self._is_panel_menu(menu)
            )
        )
        return menus.sorted(
            key=lambda menu: (
                self._menu_path(menu).lower(),
                menu.sequence,
                menu.name.lower(),
            )
        )

    def _favorite_menu_ids(self):
        raw_value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(self._favorite_param_key(), "[]")
        )
        try:
            values = json.loads(raw_value)
        except (TypeError, ValueError):
            return []
        if not isinstance(values, list):
            return []
        menu_ids = []
        for value in values:
            menu_id = self._as_int(value)
            if menu_id > 0 and menu_id not in menu_ids:
                menu_ids.append(menu_id)
        return menu_ids

    def _write_favorite_menu_ids(self, menu_ids):
        clean_ids = []
        for value in menu_ids:
            menu_id = self._as_int(value)
            if menu_id > 0 and menu_id not in clean_ids:
                clean_ids.append(menu_id)
        (
            self.env["ir.config_parameter"]
            .sudo()
            .set_param(self._favorite_param_key(), json.dumps(clean_ids))
        )

    def _favorite_param_key(self):
        return f"lqa_admin_panel.favorite_menu_ids.user_{self.env.user.id}"

    def _serialize_favorite_menus(self):
        return [
            self._serialize_favorite_menu(menu)
            for menu in self._favorite_menus()
        ]

    def _serialize_favorite_menu(self, menu):
        path_parts = self._menu_path_parts(menu)
        return {
            "menu_id": menu.id,
            "name": menu.name,
            "path": " / ".join(path_parts[:-1]),
            "full_path": " / ".join(path_parts),
            "action_id": menu.action.id if menu.action else False,
        }

    def _menu_path(self, menu):
        return " / ".join(self._menu_path_parts(menu))

    def _menu_path_parts(self, menu):
        root = self.env.ref("lqa_admin_panel.menu_lqa_root", raise_if_not_found=False)
        parts = []
        current = menu
        while current and (not root or current.id != root.id):
            parts.append(current.name)
            current = current.parent_id
        return list(reversed(parts))

    def _is_panel_menu(self, menu):
        root = self.env.ref("lqa_admin_panel.menu_lqa_root", raise_if_not_found=False)
        if not root:
            return False
        current = menu
        while current:
            if current.id == root.id:
                return True
            current = current.parent_id
        return False

    def _check_access(self):
        if not self.env.user.has_group(
            "lqa_admin_panel.group_lqa_commercial_user"
        ):
            raise AccessError(_("No tenes permisos para acceder al panel comercial."))

    @staticmethod
    def _as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
