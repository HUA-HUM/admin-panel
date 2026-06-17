/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ORDER_MARKETPLACES = [
    { id: "fravega", name: "Fravega" },
    { id: "megatone", name: "Megatone" },
    { id: "oncity", name: "OnCity" },
];

const emptyOverview = () => ({
    mode: "last24",
    range: { from: "", to: "" },
    total: 0,
    marketplaces: [],
    items: [],
    errors: [],
});

const toDateInput = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
};

const defaultCustomRange = () => {
    const today = new Date();
    const from = new Date(today);
    from.setDate(today.getDate() - 7);
    return {
        marketplace: "all",
        from: toDateInput(from),
        to: toDateInput(today),
    };
};

export class LqaRetailersOrders extends Component {
    static template = "lqa_admin_panel.RetailersOrders";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            loading: false,
            activeMode: "last24",
            overview: emptyOverview(),
            custom: defaultCustomRange(),
        });

        onMounted(() => this.loadMode("last24"));
    }

    get marketplaceBreakdown() {
        const totals = new Map();
        for (const item of this.state.overview.marketplaces || []) {
            const marketplace = String(item.marketplace || "").toLowerCase();
            if (marketplace) {
                totals.set(marketplace, Number(item.total || 0));
            }
        }
        const cards = ORDER_MARKETPLACES.map((marketplace) => ({
            ...marketplace,
            total: totals.get(marketplace.id) || 0,
        }));
        for (const [marketplace, total] of totals.entries()) {
            if (!ORDER_MARKETPLACES.some((item) => item.id === marketplace)) {
                cards.push({
                    id: marketplace,
                    name: this.marketplaceLabel(marketplace),
                    total,
                });
            }
        }
        return cards;
    }

    get rangeLabel() {
        const range = this.state.overview.range || {};
        if (range.from || range.to) {
            return `${this.formatDateTime(range.from)} - ${this.formatDateTime(range.to)}`;
        }
        return this.modeLabel(this.state.activeMode);
    }

    get totalErrors() {
        return (this.state.overview.errors || []).length;
    }

    async loadMode(mode) {
        this.state.loading = true;
        this.state.activeMode = mode;
        try {
            this.state.overview = await this.orm.call(
                "lqa.retailers.service",
                "get_orders_overview",
                [mode, {}]
            );
        } catch (error) {
            this.state.overview = emptyOverview();
            this.notifyError(error, "No se pudieron cargar las ordenes.");
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        if (this.state.activeMode === "custom") {
            await this.applyCustomRange();
            return;
        }
        await this.loadMode(this.state.activeMode || "last24");
    }

    async applyCustomRange() {
        if (!this.state.custom.from || !this.state.custom.to) {
            this.notification.add("Indica fecha desde y hasta.", { type: "warning" });
            return;
        }
        this.state.loading = true;
        this.state.activeMode = "custom";
        try {
            this.state.overview = await this.orm.call(
                "lqa.retailers.service",
                "get_orders_overview",
                [
                    "custom",
                    {
                        marketplace: this.state.custom.marketplace,
                        from: this.dateInputToIso(this.state.custom.from, false),
                        to: this.dateInputToIso(this.state.custom.to, true),
                    },
                ]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el rango seleccionado.");
        } finally {
            this.state.loading = false;
        }
    }

    dateInputToIso(value, endOfDay) {
        return `${value}T${endOfDay ? "23:59:59.000Z" : "00:00:00.000Z"}`;
    }

    modeLabel(mode) {
        return (
            {
                last24: "Ultimas 24h",
                recent24: "Recent 24h",
                recent48: "Recent 48h",
                recent72: "Recent 72h",
                historical: "Historico",
                custom: "Rango custom",
            }[mode] || "Ordenes"
        );
    }

    marketplaceLabel(value) {
        return (
            {
                fravega: "Fravega",
                megatone: "Megatone",
                oncity: "OnCity",
                "sin-marketplace": "Sin marketplace",
            }[String(value || "").toLowerCase()] || this.humanize(value)
        );
    }

    statusLabel(value) {
        return (
            {
                PAID: "Pagada",
                CANCELLED: "Cancelada",
                CANCELED: "Cancelada",
                PENDING: "Pendiente",
                PROCESSING: "Procesando",
                ERROR: "Error",
                FAILED: "Fallida",
                SUCCESS: "Correcta",
            }[String(value || "").toUpperCase()] || this.humanize(value)
        );
    }

    statusClass(value) {
        const normalized = String(value || "").toUpperCase();
        if (["PAID", "SUCCESS", "COMPLETED"].includes(normalized)) {
            return "is-green";
        }
        if (["CANCELLED", "CANCELED", "ERROR", "FAILED"].includes(normalized)) {
            return "is-red";
        }
        if (["PENDING", "PROCESSING", "IN_PROGRESS"].includes(normalized)) {
            return "is-blue";
        }
        return "is-gray";
    }

    humanize(value) {
        const cleanValue = String(value || "").trim();
        if (!cleanValue) {
            return "Sin dato";
        }
        return cleanValue
            .toLowerCase()
            .replace(/[_-]+/g, " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase());
    }

    formatNumber(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0";
        }
        return new Intl.NumberFormat("es-AR").format(numericValue);
    }

    formatCurrency(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "-";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: "ARS",
            maximumFractionDigits: 0,
        }).format(numericValue);
    }

    formatDateTime(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }
}

registry.category("actions").add("lqa_admin_panel.retailers_orders", LqaRetailersOrders);
