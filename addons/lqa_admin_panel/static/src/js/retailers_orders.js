/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MARKETPLACE_LABELS = {
    fravega: "Frávega",
    megatone: "Megatone",
    oncity: "OnCity",
    mercadolibre: "MercadoLibre",
};

const STATUS_LABELS = {
    PENDING: "Pendiente",
    PROCESSED_FLOXU: "Procesada en Floxu",
    COMPLETED: "Completada",
    CANCELLED: "Cancelada",
    FAILED: "Fallida",
};

const STATUS_CLASSES = {
    PENDING: "is-amber",
    PROCESSED_FLOXU: "is-blue",
    COMPLETED: "is-green",
    CANCELLED: "is-muted",
    FAILED: "is-red",
};

const emptyFilters = () => ({
    marketplace: "",
    persistenceStatus: "",
    from: "",
    to: "",
    search: "",
    limit: 50,
    offset: 0,
});

export class LqaRetailersOrders extends Component {
    static template = "lqa_admin_panel.RetailersOrders";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            items: [],
            pagination: {},
            filters: emptyFilters(),
            options: { marketplaces: [], statuses: [], pageSizes: [50] },
            selected: null,
            loadingDetail: false,
        });

        onWillStart(async () => {
            await this.loadOptions();
            await this.search(0);
        });
    }

    async loadOptions() {
        try {
            this.state.options = await this.orm.call(
                "lqa.retailers.service",
                "get_retailer_order_options",
                []
            );
        } catch {
            // Si no llegan, los filtros quedan con el valor por defecto.
        }
    }

    async search(offset = 0) {
        this.state.loading = true;
        this.state.filters.offset = Math.max(offset, 0);
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "get_retailer_orders",
                [{ ...this.state.filters }]
            );
            this.state.items = result.items || [];
            this.state.pagination = result.pagination || {};
        } catch (error) {
            this.state.items = [];
            this.state.pagination = {};
            this.notifyError(error, "No se pudieron cargar las órdenes.");
        } finally {
            this.state.loading = false;
        }
    }

    applyFilters() {
        // Cualquier cambio de filtro vuelve a la primera página: mantener el
        // offset mostraria una pagina vacia de un resultado mas chico.
        this.search(0);
    }

    clearFilters() {
        this.state.filters = emptyFilters();
        this.search(0);
    }

    get hasFilters() {
        const f = this.state.filters;
        return Boolean(
            f.marketplace || f.persistenceStatus || f.from || f.to || f.search
        );
    }

    nextPage() {
        if (this.state.pagination.hasNext) {
            this.search(this.state.pagination.nextOffset);
        }
    }

    previousPage() {
        if (this.state.pagination.hasPrevious) {
            this.search(this.state.pagination.previousOffset);
        }
    }

    async openOrder(order) {
        this.state.selected = order;
        this.state.loadingDetail = true;
        try {
            this.state.selected = await this.orm.call(
                "lqa.retailers.service",
                "get_retailer_order_detail",
                [order.uniqueKey]
            );
        } catch (error) {
            // El detalle completo fallo, pero la fila ya trae lo esencial.
            this.notifyError(error, "No se pudo cargar el detalle completo.");
        } finally {
            this.state.loadingDetail = false;
        }
    }

    closeOrder() {
        this.state.selected = null;
    }

    marketplaceLabel(code) {
        return MARKETPLACE_LABELS[code] || this.humanize(code);
    }

    statusLabel(status) {
        return STATUS_LABELS[status] || this.humanize(status);
    }

    statusClass(status) {
        return STATUS_CLASSES[status] || "is-muted";
    }

    get selectedPayload() {
        const sel = this.state.selected;
        if (!sel) {
            return "";
        }
        const raw = sel.normalizedPayload || sel.sourcePayload;
        if (!raw) {
            return "";
        }
        try {
            return JSON.stringify(
                typeof raw === "string" ? JSON.parse(raw) : raw,
                null,
                2
            );
        } catch {
            return String(raw);
        }
    }

    get shippingLine() {
        const sel = this.state.selected;
        if (!sel) {
            return "";
        }
        return [sel.shippingAddress, sel.shippingCity, sel.shippingProvince, sel.shippingZipCode]
            .filter(Boolean)
            .join(", ");
    }

    humanize(value) {
        const text = String(value || "").replace(/[_-]+/g, " ").trim();
        return text ? text.charAt(0).toUpperCase() + text.slice(1).toLowerCase() : "-";
    }

    formatNumber(value) {
        return new Intl.NumberFormat("es-AR").format(Number(value || 0));
    }

    formatCurrency(value, currency = "ARS") {
        const amount = Number(value || 0);
        try {
            return new Intl.NumberFormat("es-AR", {
                style: "currency",
                currency: currency || "ARS",
                maximumFractionDigits: 0,
            }).format(amount);
        } catch {
            return `$ ${this.formatNumber(amount)}`;
        }
    }

    formatDateTime(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        return date.toLocaleString("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || error?.message || fallback, {
            type: "danger",
        });
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.retailers_orders", LqaRetailersOrders);
