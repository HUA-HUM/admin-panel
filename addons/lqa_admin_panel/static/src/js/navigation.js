/** @odoo-module **/

import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { NavBar } from "@web/webclient/navbar/navbar";

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.lqaOrm = useService("orm");
        this.lqaNotification = useService("notification");
        this.lqaNavigation = useState({
            mobileOpen: false,
            expanded: {},
            panelRootMenuId: false,
            favoriteMenuIds: {},
            favoritePending: {},
        });
        onWillStart(async () => {
            await this.lqaLoadFavorites();
        });
    },

    get lqaShouldShowSidebar() {
        return Boolean(this.lqaActiveAreaSection(this.lqaPanelRootSections()));
    },

    get lqaSidebarSections() {
        const rootSections = this.lqaPanelRootSections();
        if (rootSections.length) {
            const activeArea = this.lqaActiveAreaSection(rootSections);
            if (!activeArea) {
                return [];
            }
            return activeArea.childrenTree?.length
                ? activeArea.childrenTree
                : [activeArea];
        }
        return this.currentAppSections || [];
    },

    lqaPanelRootSections() {
        const panelRoot = this.lqaPanelRootMenu();
        if (Array.isArray(panelRoot?.childrenTree) && panelRoot.childrenTree.length) {
            return panelRoot.childrenTree;
        }
        return [];
    },

    lqaPanelRootMenu() {
        const rootId = this.lqaNavigation.panelRootMenuId;
        if (!rootId || !this.menuService?.getMenu) {
            return null;
        }
        try {
            return this.menuService.getMenu(rootId);
        } catch {
            return null;
        }
    },

    lqaIsExpanded(section) {
        return this.lqaNavigation.expanded[section.id] !== false;
    },

    lqaCurrentMenu() {
        try {
            return this.menuService?.getCurrentMenu?.() || null;
        } catch {
            return null;
        }
    },

    lqaCurrentAction() {
        const actionService = this.actionService || this.env?.services?.action;
        try {
            return actionService?.currentController?.action || null;
        } catch {
            return null;
        }
    },

    lqaActiveAreaSection(rootSections) {
        const panelRootId = Number(this.lqaNavigation.panelRootMenuId || 0);
        const currentNames = [
            this.lqaCurrentMenu()?.name,
            this.currentApp?.name,
        ]
            .map((name) => String(name || "").trim().toLowerCase())
            .filter(Boolean);
        const currentIds = [
            this.lqaCurrentMenu()?.id,
            this.currentApp?.id,
        ]
            .map((id) => Number(id || 0))
            .filter((id) => id && id !== panelRootId);
        const currentActionIds = [
            this.lqaCurrentAction()?.id,
            this.lqaCurrentAction()?.action_id,
            this.lqaCurrentAction()?.actionId,
        ]
            .map((id) => Number(id || 0))
            .filter(Boolean);
        if (!currentIds.length && !currentActionIds.length) {
            return this.lqaActiveAreaFromAction(rootSections);
        }
        return (
            rootSections.find((section) =>
                currentNames.includes(String(section.name || "").trim().toLowerCase())
            ) ||
            rootSections.find((section) =>
                currentIds.some((id) => this.lqaMenuContains(section, id)) ||
                currentActionIds.some((id) => this.lqaMenuContainsAction(section, id))
            ) ||
            this.lqaActiveAreaFromAction(rootSections) ||
            null
        );
    },

    lqaActiveAreaFromAction(rootSections) {
        const action = this.lqaCurrentAction();
        const areaName = this.lqaAreaNameFromAction(action);
        if (!areaName) {
            return null;
        }
        return (
            rootSections.find(
                (section) =>
                    String(section.name || "").trim().toLowerCase() === areaName
            ) || null
        );
    },

    lqaAreaNameFromAction(action) {
        const params = action?.params || {};
        const areaCode = String(params.area_code || "").toLowerCase();
        const moduleCode = String(params.module_code || "").toLowerCase();
        const tag = String(action?.tag || "").toLowerCase();
        const name = String(action?.name || "").toLowerCase();
        const resModel = String(action?.res_model || "").toLowerCase();

        if (
            areaCode === "comercial" ||
            ["mercadolibre", "automeli", "retailers"].includes(moduleCode) ||
            tag.includes("mercadolibre") ||
            tag.includes("automeli") ||
            tag.includes("retailers") ||
            tag.includes("google_merchant")
        ) {
            return "comercial";
        }
        if (
            areaCode === "administracion" ||
            moduleCode === "administracion" ||
            tag.includes("accounting") ||
            name.includes("administracion") ||
            name.includes("facturacion") ||
            name.includes("clientes")
        ) {
            return "administracion";
        }
        if (
            areaCode === "configuracion" ||
            tag.includes("user_management") ||
            resModel === "res.config.settings" ||
            name.includes("configuracion") ||
            name.includes("usuarios")
        ) {
            return "configuracion";
        }
        return "";
    },

    lqaMenuContains(menu, menuId) {
        if (!menu || !menuId) {
            return false;
        }
        if (Number(menu.id) === Number(menuId)) {
            return true;
        }
        return (menu.childrenTree || []).some((child) =>
            this.lqaMenuContains(child, menuId)
        );
    },

    lqaMenuContainsAction(menu, actionId) {
        if (!menu || !actionId) {
            return false;
        }
        const menuActionId = Number(menu.actionID || menu.actionId || 0);
        if (menuActionId && menuActionId === Number(actionId)) {
            return true;
        }
        return (menu.childrenTree || []).some((child) =>
            this.lqaMenuContainsAction(child, actionId)
        );
    },

    lqaToggleSection(section) {
        this.lqaNavigation.expanded[section.id] = !this.lqaIsExpanded(section);
    },

    lqaOpenMobileSidebar() {
        if (!this.lqaShouldShowSidebar) {
            return;
        }
        this.lqaNavigation.mobileOpen = true;
    },

    lqaCloseMobileSidebar() {
        this.lqaNavigation.mobileOpen = false;
    },

    lqaCanFavorite(menu) {
        const currentApp = this.currentApp;
        const isPanelApp =
            currentApp?.xmlid === "lqa_admin_panel.menu_lqa_root" ||
            currentApp?.xmlID === "lqa_admin_panel.menu_lqa_root" ||
            currentApp?.name === "Panel Comercial" ||
            currentApp?.name === "Panel Interno" ||
            (
                this.lqaNavigation.panelRootMenuId &&
                Number(currentApp?.id) ===
                    Number(this.lqaNavigation.panelRootMenuId)
            ) ||
            this.lqaMenuContains(this.lqaPanelRootMenu(), currentApp?.id);
        return Boolean(
            isPanelApp && (menu?.actionID || menu?.actionId || menu?.action)
        );
    },

    lqaIsFavorite(menu) {
        return Boolean(this.lqaNavigation.favoriteMenuIds[menu?.id]);
    },

    lqaFavoriteTitle(menu) {
        return this.lqaIsFavorite(menu)
            ? `Quitar ${menu.name} de favoritos`
            : `Agregar ${menu.name} a favoritos`;
    },

    async lqaLoadFavorites() {
        try {
            const data = await this.lqaOrm.call(
                "lqa.dashboard.service",
                "get_menu_favorites_state",
                []
            );
            this.lqaSetFavoriteState(data);
        } catch (error) {
            this.lqaNavigation.favoriteMenuIds = {};
            if (["Panel Comercial", "Panel Interno"].includes(this.currentApp?.name)) {
                this.lqaNavigation.panelRootMenuId = this.currentApp.id;
            }
            console.warn("No se pudieron cargar los favoritos del panel.", error);
        }
    },

    lqaSetFavoriteState(data) {
        const favoriteMenuIds = {};
        for (const menuId of data?.favorite_menu_ids || []) {
            favoriteMenuIds[menuId] = true;
        }
        this.lqaNavigation.panelRootMenuId = data?.panel_root_menu_id || false;
        this.lqaNavigation.favoriteMenuIds = favoriteMenuIds;
        this.env.bus.trigger("lqa-favorites-changed", {
            favorites: data?.favorites || [],
        });
    },

    async lqaToggleFavorite(menu, event) {
        event.stopPropagation();
        if (!this.lqaCanFavorite(menu) || this.lqaNavigation.favoritePending[menu.id]) {
            return;
        }
        this.lqaNavigation.favoritePending[menu.id] = true;
        try {
            const wasFavorite = this.lqaIsFavorite(menu);
            const data = await this.lqaOrm.call(
                "lqa.dashboard.service",
                "toggle_menu_favorite",
                [menu.id]
            );
            this.lqaSetFavoriteState(data);
            this.lqaNotification.add(
                wasFavorite
                    ? `${menu.name} se quitó de favoritos.`
                    : `${menu.name} se agregó a favoritos.`,
                { type: "success" }
            );
        } catch (error) {
            this.lqaNotification.add(
                error?.data?.message || "No se pudo actualizar el favorito.",
                { type: "danger" }
            );
        } finally {
            delete this.lqaNavigation.favoritePending[menu.id];
        }
    },

    async lqaOpenPanelHome() {
        const rootMenu = this.lqaPanelRootMenu() || this.currentApp;
        await this.lqaSelectMenu(rootMenu);
    },

    async lqaSelectMenu(menu) {
        if (!menu?.actionID) {
            return;
        }
        await this.actionService.doAction(menu.actionID, {
            clearBreadcrumbs: true,
            noEmptyTransition: true,
            onActionReady: () => {
                this.menuService.setCurrentMenu(menu);
            },
        });
        this.lqaCloseMobileSidebar();
    },
});
