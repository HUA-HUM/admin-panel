/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class LqaAccounting extends Component {
    static template = "lqa_admin_panel.Accounting";

    setup() {
        const params = this.props.action?.params || {};
        this.state = useState({
            view: params.view || "dashboard",
        });
    }

    get isDashboard() {
        return this.state.view === "dashboard";
    }

    get isArcaBilling() {
        return this.state.view === "arca_billing";
    }

    get pageTitle() {
        return this.isArcaBilling ? "Facturacion ARCA" : "Administracion";
    }

    get pageSubtitle() {
        return this.isArcaBilling
            ? "Comprobantes fiscales para ordenes de venta."
            : "Area administrativa, contable y fiscal.";
    }

    openDashboard() {
        this.state.view = "dashboard";
    }

    openArcaBilling() {
        this.state.view = "arca_billing";
    }
}

registry.category("actions").add("lqa_admin_panel.accounting", LqaAccounting);
