/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const blankForm = () => ({
    id: null,
    name: "",
    login: "",
    email: "",
    role: "commercial",
    active: true,
    password: "",
});

export class LqaUserManagement extends Component {
    static template = "lqa_admin_panel.UserManagement";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            saving: false,
            users: [],
            query: "",
            form: blankForm(),
        });

        onMounted(() => this.loadUsers());
    }

    async loadUsers() {
        this.state.loading = true;
        try {
            this.state.users = await this.orm.call(
                "lqa.user.management.service",
                "get_users",
                []
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar los usuarios.");
        } finally {
            this.state.loading = false;
        }
    }

    async saveUser() {
        this.state.saving = true;
        try {
            const payload = { ...this.state.form };
            if (payload.id) {
                const updated = await this.orm.call(
                    "lqa.user.management.service",
                    "update_user",
                    [payload.id, payload]
                );
                this.replaceUser(updated);
                this.notification.add("Usuario actualizado.", { type: "success" });
            } else {
                const created = await this.orm.call(
                    "lqa.user.management.service",
                    "create_user",
                    [payload]
                );
                this.state.users.unshift(created);
                this.notification.add("Usuario creado.", { type: "success" });
            }
            this.state.form = blankForm();
        } catch (error) {
            this.notifyError(error, "No se pudo guardar el usuario.");
        } finally {
            this.state.saving = false;
        }
    }

    editUser(user) {
        this.state.form = {
            id: user.id,
            name: user.name,
            login: user.login,
            email: user.email,
            role: user.role === "admin" ? "admin" : "commercial",
            active: user.active,
            password: "",
        };
    }

    resetForm() {
        this.state.form = blankForm();
    }

    replaceUser(user) {
        const index = this.state.users.findIndex((item) => item.id === user.id);
        if (index >= 0) {
            this.state.users.splice(index, 1, user);
        }
    }

    get filteredUsers() {
        const query = this.state.query.trim().toLowerCase();
        if (!query) {
            return this.state.users;
        }
        return this.state.users.filter((user) =>
            [user.name, user.login, user.email, user.role_label]
                .join(" ")
                .toLowerCase()
                .includes(query)
        );
    }

    get userSummary() {
        return {
            total: this.state.users.length,
            active: this.state.users.filter((user) => user.active).length,
            admins: this.state.users.filter((user) => user.role === "admin").length,
            commercial: this.state.users.filter((user) => user.role === "commercial").length,
        };
    }

    get isEditing() {
        return Boolean(this.state.form.id);
    }

    initials(name) {
        const parts = String(name || "")
            .trim()
            .split(/\s+/)
            .slice(0, 2);
        return parts.map((part) => part[0]).join("").toUpperCase() || "U";
    }

    roleClass(role) {
        return role === "admin" ? "is-admin" : role === "commercial" ? "is-user" : "";
    }

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.user_management", LqaUserManagement);
