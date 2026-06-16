from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class LqaUserManagementService(models.AbstractModel):
    _name = "lqa.user.management.service"
    _description = "Servicio de usuarios del panel comercial"

    ROLE_COMMERCIAL = "commercial"
    ROLE_ADMIN = "admin"

    @api.model
    def get_users(self):
        self._check_access()
        users = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search([("share", "=", False)], order="active desc, name", limit=300)
        )
        return [self._serialize_user(user) for user in users]

    @api.model
    def create_user(self, values):
        self._check_access()
        values = values or {}
        name = self._clean(values.get("name"))
        login = self._clean(values.get("login")).lower()
        email = self._clean(values.get("email") or login).lower()
        password = values.get("password") or ""
        role = self._clean(values.get("role")) or self.ROLE_COMMERCIAL

        if not name or not login:
            raise UserError(_("Completa nombre y email/login."))
        if len(password) < 8:
            raise UserError(_("La contrasena debe tener al menos 8 caracteres."))
        if role not in {self.ROLE_COMMERCIAL, self.ROLE_ADMIN}:
            raise UserError(_("Selecciona un permiso valido."))

        existing = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search([("login", "=", login)], limit=1)
        )
        if existing:
            raise UserError(_("Ya existe un usuario con ese login."))

        company = self.env.company
        user = (
            self.env["res.users"]
            .sudo()
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": name,
                    "login": login,
                    "email": email,
                    "password": password,
                    "company_id": company.id,
                    "company_ids": [(6, 0, [company.id])],
                    "groups_id": [(6, 0, self._group_ids_for_role(role))],
                }
            )
        )
        return self._serialize_user(user)

    @api.model
    def update_user(self, user_id, values):
        self._check_access()
        user = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .browse(int(user_id or 0))
        )
        if not user.exists():
            raise UserError(_("El usuario no existe."))

        values = values or {}
        role = self._clean(values.get("role")) or self._role_for_user(user)
        active = bool(values.get("active", user.active))
        if user.id == self.env.uid and (not active or role != self.ROLE_ADMIN):
            raise UserError(_("No podes quitarte tu propio acceso administrador."))

        write_values = {
            "name": self._clean(values.get("name")) or user.name,
            "email": self._clean(values.get("email")) or user.email,
            "active": active,
        }
        password = values.get("password") or ""
        if password:
            if len(password) < 8:
                raise UserError(_("La contrasena debe tener al menos 8 caracteres."))
            write_values["password"] = password

        login = self._clean(values.get("login")).lower()
        if login and login != user.login:
            existing = (
                self.env["res.users"]
                .sudo()
                .with_context(active_test=False)
                .search([("login", "=", login), ("id", "!=", user.id)], limit=1)
            )
            if existing:
                raise UserError(_("Ya existe un usuario con ese login."))
            write_values["login"] = login

        user.write(write_values)
        self._apply_role(user, role)
        return self._serialize_user(user)

    def _check_access(self):
        if not self.env.user.has_group("lqa_admin_panel.group_lqa_admin"):
            raise AccessError(_("No tenes permisos para administrar usuarios."))

    def _serialize_user(self, user):
        return {
            "id": user.id,
            "name": user.name,
            "login": user.login,
            "email": user.email or "",
            "active": user.active,
            "role": self._role_for_user(user),
            "role_label": self._role_label(user),
            "is_current_user": user.id == self.env.uid,
        }

    def _role_for_user(self, user):
        if user.has_group("lqa_admin_panel.group_lqa_admin"):
            return self.ROLE_ADMIN
        if user.has_group("lqa_admin_panel.group_lqa_commercial_user"):
            return self.ROLE_COMMERCIAL
        return "none"

    def _role_label(self, user):
        role = self._role_for_user(user)
        return {
            self.ROLE_ADMIN: "Administrador del panel",
            self.ROLE_COMMERCIAL: "Usuario comercial",
        }.get(role, "Sin acceso panel")

    def _group_ids_for_role(self, role):
        groups = [
            self.env.ref("base.group_user").id,
            self.env.ref("lqa_admin_panel.group_lqa_commercial_user").id,
        ]
        if role == self.ROLE_ADMIN:
            groups.append(self.env.ref("lqa_admin_panel.group_lqa_admin").id)
        return groups

    def _apply_role(self, user, role):
        if role not in {self.ROLE_COMMERCIAL, self.ROLE_ADMIN}:
            raise UserError(_("Selecciona un permiso valido."))

        commercial = self.env.ref("lqa_admin_panel.group_lqa_commercial_user")
        admin = self.env.ref("lqa_admin_panel.group_lqa_admin")
        internal = self.env.ref("base.group_user")
        commands = [(4, internal.id), (4, commercial.id)]
        if role == self.ROLE_ADMIN:
            commands.append((4, admin.id))
        else:
            commands.append((3, admin.id))
        user.write({"groups_id": commands})

    @staticmethod
    def _clean(value):
        return str(value or "").strip()
