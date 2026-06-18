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

    get lqaSidebarSections() {
        return this.currentAppSections;
    },

    lqaIsExpanded(section) {
        return this.lqaNavigation.expanded[section.id] !== false;
    },

    lqaToggleSection(section) {
        this.lqaNavigation.expanded[section.id] = !this.lqaIsExpanded(section);
    },

    lqaOpenMobileSidebar() {
        this.lqaNavigation.mobileOpen = true;
    },

    lqaCloseMobileSidebar() {
        this.lqaNavigation.mobileOpen = false;
    },

    lqaCanFavorite(menu) {
        const isPanelApp =
            Number(this.currentApp?.id) === Number(this.lqaNavigation.panelRootMenuId);
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
        } catch {
            this.lqaNavigation.favoriteMenuIds = {};
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

    async lqaSelectMenu(menu) {
        await this.menuService.selectMenu(menu);
        this.lqaCloseMobileSidebar();
    },
});
