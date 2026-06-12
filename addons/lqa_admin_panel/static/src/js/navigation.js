/** @odoo-module **/

import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.lqaNavigation = useState({
            mobileOpen: false,
            expanded: {},
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

    async lqaSelectMenu(menu) {
        await this.menuService.selectMenu(menu);
        this.lqaCloseMobileSidebar();
    },
});
