/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";

export class LqaAdminDashboard extends Component {
    static template = "lqa_admin_panel.Dashboard";

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        const params = this.props.action?.params || {};

        this.state = useState({
            loading: true,
            environment: "",
            apiConfigured: false,
            modules: [],
            navigationModules: [],
            selectedModuleCode: params.module_code || false,
            favorites: [],
        });

        useBus(this.env.bus, "lqa-favorites-changed", ({ detail }) => {
            this.state.favorites = detail?.favorites || [];
        });

        onWillStart(async () => {
            await this.loadDashboard();
        });
    }

    async loadDashboard(moduleCode = this.state.selectedModuleCode) {
        this.state.loading = true;
        try {
            const data = await this.orm.call("lqa.dashboard.service", "get_dashboard_state", [
                moduleCode,
            ]);
            this.state.environment = data.environment;
            this.state.apiConfigured = data.api_configured;
            this.state.modules = data.modules;
            this.state.navigationModules = data.navigation_modules;
            this.state.selectedModuleCode = data.selected_module_code;
            this.state.favorites = data.favorites || [];
        } catch (error) {
            this.notification.add("No se pudo cargar el dashboard comercial.", {
                type: "danger",
            });
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    async openModule(module) {
        if (module.action_id) {
            await this.action.doAction(module.action_id);
            return;
        }
        await this.loadDashboard(module.code);
    }

    openSection(section) {
        if (section.action_id) {
            this.action.doAction(section.action_id);
            return;
        }
        this.notification.add("Esta seccion esta preparada para definir mas adelante.", {
            type: "info",
        });
    }

    async openFavorite(favorite) {
        if (favorite.action_id) {
            await this.action.doAction(favorite.action_id);
        }
    }

    favoriteIcon(favorite) {
        const name = String(favorite.name || "").toLowerCase();
        if (name === "dashboard") {
            return "fa fa-line-chart";
        }
        if (name.includes("catalog")) {
            return "fa fa-th";
        }
        if (name.includes("marketplace")) {
            return "fa fa-shopping-cart";
        }
        if (name.includes("pricing")) {
            return "fa fa-usd";
        }
        if (name.includes("public")) {
            return "fa fa-cloud-upload";
        }
        if (name.includes("order") || name.includes("seguimiento")) {
            return "fa fa-list-alt";
        }
        if (name.includes("carpeta") || name.includes("seleccion")) {
            return "fa fa-folder-open-o";
        }
        if (name.includes("promocion")) {
            return "fa fa-bullhorn";
        }
        return "fa fa-star";
    }
}

registry.category("actions").add("lqa_admin_panel.dashboard", LqaAdminDashboard);
