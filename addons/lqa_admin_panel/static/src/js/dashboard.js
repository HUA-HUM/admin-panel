/** @odoo-module **/

import {
    Component,
    onMounted,
    onPatched,
    onWillStart,
    onWillUnmount,
    useState,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";

export class LqaAdminDashboard extends Component {
    static template = "lqa_admin_panel.Dashboard";

    setup() {
        this.action = useService("action");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.orm = useService("orm");
        const params = this.props.action?.params || {};

        this.state = useState({
            loading: true,
            areas: [],
            areaCode: params.area_code || false,
            modules: [],
            selectedModuleCode: params.module_code || false,
            favorites: [],
        });

        useBus(this.env.bus, "lqa-favorites-changed", ({ detail }) => {
            this.state.favorites = detail?.favorites || [];
        });

        this.updateRootDashboardClass();
        onMounted(() => this.updateRootDashboardClass());
        onPatched(() => this.updateRootDashboardClass());
        onWillUnmount(() => {
            document.body.classList.remove("o_lqa_root_dashboard");
        });

        onWillStart(async () => {
            await this.loadDashboard();
        });
    }

    updateRootDashboardClass() {
        document.body.classList.toggle("o_lqa_root_dashboard", this.isRootDashboard);
    }

    async loadDashboard(
        moduleCode = this.state.selectedModuleCode,
        areaCode = this.state.areaCode
    ) {
        this.state.loading = true;
        try {
            const data = await this.orm.call("lqa.dashboard.service", "get_dashboard_state", [
                moduleCode,
                areaCode,
            ]);
            this.state.areas = data.areas || [];
            this.state.modules = data.modules;
            this.state.areaCode = data.selected_area_code;
            this.state.selectedModuleCode = data.selected_module_code;
            this.state.favorites = data.favorites || [];
        } catch (error) {
            this.notification.add("No se pudo cargar el dashboard interno.", {
                type: "danger",
            });
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    get selectedModule() {
        return this.state.modules.find(
            (module) => module.code === this.state.selectedModuleCode
        );
    }

    get selectedArea() {
        return this.state.areas.find(
            (area) => area.code === this.state.areaCode
        );
    }

    get isRootDashboard() {
        return !this.state.areaCode && !this.state.selectedModuleCode;
    }

    get showsModules() {
        return Boolean(this.state.areaCode || this.state.selectedModuleCode);
    }

    get availableSectionsCount() {
        if (this.isRootDashboard) {
            return this.state.areas.reduce(
                (total, area) => total + (area.section_count || 0),
                0
            );
        }
        return this.state.modules.reduce(
            (total, module) => total + (module.sections || []).length,
            0
        );
    }

    get activeModulesCount() {
        if (this.isRootDashboard) {
            return this.state.areas.length;
        }
        return this.state.modules.length;
    }

    get dashboardTitle() {
        return this.selectedModule?.name || this.selectedArea?.name || "Panel principal";
    }

    get dashboardSubtitle() {
        return (
            this.selectedModule?.description ||
            this.selectedArea?.description ||
            "Vista general de las areas internas."
        );
    }

    get dashboardEyebrow() {
        if (this.selectedModule) {
            return `${this.selectedArea?.name || "Area"} / Dashboard`;
        }
        if (this.selectedArea) {
            return "Area / Dashboard";
        }
        return "Panel interno";
    }

    areaIcon(area) {
        if (area.code === "comercial") {
            return "fa fa-briefcase";
        }
        if (area.code === "administracion") {
            return "fa fa-calculator";
        }
        if (area.code === "configuracion") {
            return "fa fa-sliders";
        }
        return "fa fa-cubes";
    }

    areaCardClass(area) {
        return `o_lqa_dashboard_area is-${area.code || "default"}`;
    }

    areaSummary(area) {
        if (area.summary) {
            return area.summary;
        }
        if (area.module_count === 1) {
            return "1 modulo";
        }
        return `${area.module_count || 0} modulos`;
    }

    openArea(area) {
        if (area.action_id) {
            let menu = null;
            try {
                menu = area.menu_id ? this.menu.getMenu(area.menu_id) : null;
            } catch {
                menu = null;
            }
            this.openAction(area.action_id, menu);
        }
    }

    openModule(module) {
        if (module.action_id) {
            this.openAction(module.action_id);
        }
    }

    openSection(section) {
        if (section.action_id) {
            this.openAction(section.action_id);
            return;
        }
        this.notification.add("Esta seccion esta preparada para definir mas adelante.", {
            type: "info",
        });
    }

    async openFavorite(favorite) {
        if (favorite.action_id) {
            const menu = this.menu.getMenu(favorite.menu_id);
            await this.openAction(favorite.action_id, menu);
        }
    }

    async openAction(actionId, menu = null) {
        await this.action.doAction(actionId, {
            clearBreadcrumbs: true,
            noEmptyTransition: true,
            onActionReady: () => {
                if (menu) {
                    this.menu.setCurrentMenu(menu);
                }
            },
        });
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
        if (name.includes("eliminador")) {
            return "fa fa-trash-o";
        }
        if (name.includes("acciones")) {
            return "fa fa-bolt";
        }
        if (name.includes("facturacion") || name.includes("arca")) {
            return "fa fa-file-text-o";
        }
        if (name.includes("contable") || name.includes("administracion")) {
            return "fa fa-calculator";
        }
        return "fa fa-star";
    }
}

registry.category("actions").add("lqa_admin_panel.dashboard", LqaAdminDashboard);
