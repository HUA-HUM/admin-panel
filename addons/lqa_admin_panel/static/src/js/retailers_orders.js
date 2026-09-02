/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const emptyOrders = () => ({
    items: [],
    pagination: {
        page: 1,
        perPage: 15,
        total: 0,
        totalPages: 1,
        from: 0,
        to: 0,
        hasPrevious: false,
        hasNext: false,
    },
});

export class LqaRetailersOrders extends Component {
    static template = "lqa_admin_panel.RetailersOrders";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            orders: emptyOrders(),
            search: "",
            selectedOrderId: "",
            detail: null,
            loadingDetail: false,
            detailError: "",
            showRaw: false,
        });
        onMounted(() => this.loadOrders(1));
    }

    get visibleOrders() {
        const query = String(this.state.search || "").trim().toLowerCase();
        if (!query) {
            return this.state.orders.items || [];
        }
        return (this.state.orders.items || []).filter((order) =>
            [order.id, order.sequence, order.clientName, order.status]
                .some((value) => String(value || "").toLowerCase().includes(query))
        );
    }

    get pageStats() {
        const items = this.state.orders.items || [];
        return {
            ready: items.filter((item) => item.status === "ready-for-handling").length,
            canceled: items.filter((item) => ["canceled", "cancelled"].includes(item.status)).length,
            value: items.reduce((total, item) => total + (Number(item.total) || 0), 0),
        };
    }

    get visiblePages() {
        const pagination = this.state.orders.pagination;
        const start = Math.max(pagination.page - 2, 1);
        const end = Math.min(start + 4, pagination.totalPages);
        const adjustedStart = Math.max(end - 4, 1);
        return Array.from(
            { length: Math.max(end - adjustedStart + 1, 0) },
            (_, index) => adjustedStart + index
        );
    }

    async loadOrders(page = 1) {
        this.state.loading = true;
        try {
            this.state.orders = await this.orm.call(
                "lqa.retailers.service",
                "get_fravega_orders",
                [Number(page) || 1]
            );
        } catch (error) {
            this.state.orders = emptyOrders();
            this.notifyError(error, "No se pudieron cargar las órdenes de Frávega.");
        } finally {
            this.state.loading = false;
        }
    }

    async openOrder(order) {
        if (!order?.id) {
            return;
        }
        this.state.selectedOrderId = order.id;
        this.state.detail = null;
        this.state.detailError = "";
        this.state.showRaw = false;
        this.state.loadingDetail = true;
        try {
            this.state.detail = await this.orm.call(
                "lqa.retailers.service",
                "get_fravega_order_detail",
                [order.id]
            );
        } catch (error) {
            this.state.detailError =
                error?.data?.message || "No se pudo obtener el detalle de la orden.";
        } finally {
            this.state.loadingDetail = false;
        }
    }

    closeOrder() {
        this.state.selectedOrderId = "";
        this.state.detail = null;
        this.state.detailError = "";
        this.state.showRaw = false;
    }

    previousPage() {
        const pagination = this.state.orders.pagination;
        if (pagination.hasPrevious) {
            this.loadOrders(pagination.page - 1);
        }
    }

    nextPage() {
        const pagination = this.state.orders.pagination;
        if (pagination.hasNext) {
            this.loadOrders(pagination.page + 1);
        }
    }

    formatField(field) {
        if (!field) {
            return "-";
        }
        switch (field.type) {
            case "money":
                return this.formatCurrency(field.value);
            case "datetime":
                return this.formatDateTime(field.value);
            case "number":
                return this.formatNumber(field.value);
            case "bool":
                return field.value ? "Sí" : "No";
            default:
                return String(field.value ?? "");
        }
    }

    fieldHref(field) {
        if (field?.type === "email" && field.value) {
            return `mailto:${field.value}`;
        }
        if (field?.type === "phone" && field.value) {
            return `tel:${String(field.value).replace(/[^+\d]/g, "")}`;
        }
        return "";
    }

    itemImage(url) {
        // VTEX sirve el thumbnail de 55px; pedimos la variante mas grande.
        return url ? String(url).replace(/(\/ids\/\d+)-\d+-\d+\//, "$1-160-160/") : "";
    }

    statusLabel(value, description = "") {
        const labels = {
            "ready-for-handling": "Lista para preparar",
            "waiting-ffmt-authorization": "Esperando autorización",
            canceled: "Cancelada",
            cancelled: "Cancelada",
            invoiced: "Facturada",
            handling: "En preparación",
        };
        return labels[String(value || "").toLowerCase()] || description || this.humanize(value);
    }

    statusClass(value) {
        const normalized = String(value || "").toLowerCase();
        if (["ready-for-handling", "invoiced", "completed"].includes(normalized)) {
            return "is-green";
        }
        if (["canceled", "cancelled", "error", "failed"].includes(normalized)) {
            return "is-red";
        }
        if (["waiting-ffmt-authorization", "handling", "pending"].includes(normalized)) {
            return "is-blue";
        }
        return "is-gray";
    }

    humanize(value) {
        const cleanValue = String(value || "").trim();
        return cleanValue
            ? cleanValue.toLowerCase().replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
            : "Sin dato";
    }

    formatNumber(value) {
        return new Intl.NumberFormat("es-AR").format(Number(value) || 0);
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
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, { type: "danger" });
    }
}

registry.category("actions").add("lqa_admin_panel.retailers_orders", LqaRetailersOrders);
