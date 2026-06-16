/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const firstDayOfMonth = () => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
};

const today = () => new Date().toISOString().slice(0, 10);

const defaultPromotionFilters = () => ({
    page: 1,
    limit: "100",
    status: "",
    type: "",
    search: "",
});

const defaultCatalogFilters = () => ({
    page: 1,
    limit: "100",
    type: "",
    search: "",
});

const defaultOrderFilters = () => ({
    offset: 0,
    limit: "50",
    status: "paid",
    fromDate: firstDayOfMonth(),
    toDate: today(),
    groupBy: "day",
});

export class LqaMercadolibrePromotions extends Component {
    static template = "lqa_admin_panel.MercadolibrePromotions";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            activeTab: "central",
            loadingStats: true,
            loadingPromotions: true,
            loadingCatalogs: false,
            loadingOrders: false,
            loadingAnalytics: false,
            stats: { total: 0, cards: [] },
            promotions: { items: [], pagination: {} },
            catalogs: { items: [], summary: {}, pagination: {} },
            orders: { items: [], summary: {}, pagination: {} },
            analytics: { series: [], summary: {} },
            promotionFilters: defaultPromotionFilters(),
            catalogFilters: defaultCatalogFilters(),
            orderFilters: defaultOrderFilters(),
        });

        onWillStart(async () => {
            await Promise.all([this.loadStats(), this.loadPromotions()]);
        });
    }

    async refreshCurrent() {
        await this.loadStats();
        if (this.state.activeTab === "central") {
            await this.loadPromotions();
        } else if (this.state.activeTab === "catalogs") {
            await this.loadCatalogs();
        } else {
            await Promise.all([this.loadOrders(), this.loadAnalytics()]);
        }
    }

    async setTab(tab) {
        this.state.activeTab = tab;
        if (tab === "catalogs" && !this.state.catalogs.items.length) {
            await this.loadCatalogs();
        }
        if (tab === "orders" && !this.state.orders.items.length) {
            await Promise.all([this.loadOrders(), this.loadAnalytics()]);
        }
    }

    async loadStats() {
        this.state.loadingStats = true;
        try {
            this.state.stats = await this.orm.call(
                "lqa.mercadolibre.promotions.service",
                "get_stats",
                []
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar las estadisticas.");
        } finally {
            this.state.loadingStats = false;
        }
    }

    async loadPromotions() {
        this.state.loadingPromotions = true;
        try {
            this.state.promotions = await this.orm.call(
                "lqa.mercadolibre.promotions.service",
                "get_promotions",
                [{ ...this.state.promotionFilters }]
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar las promociones.");
        } finally {
            this.state.loadingPromotions = false;
        }
    }

    async loadCatalogs() {
        this.state.loadingCatalogs = true;
        try {
            this.state.catalogs = await this.orm.call(
                "lqa.mercadolibre.promotions.service",
                "get_catalogs",
                [{ ...this.state.catalogFilters }]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el catalogo de promociones.");
        } finally {
            this.state.loadingCatalogs = false;
        }
    }

    async loadOrders() {
        this.state.loadingOrders = true;
        try {
            this.state.orders = await this.orm.call(
                "lqa.mercadolibre.promotions.service",
                "get_orders",
                [{ ...this.state.orderFilters }]
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar las ordenes.");
        } finally {
            this.state.loadingOrders = false;
        }
    }

    async loadAnalytics() {
        this.state.loadingAnalytics = true;
        try {
            this.state.analytics = await this.orm.call(
                "lqa.mercadolibre.promotions.service",
                "get_orders_analytics",
                [{ ...this.state.orderFilters }]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el analytics de aporte ML.");
        } finally {
            this.state.loadingAnalytics = false;
        }
    }

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }

    async setPromotionStatus(status) {
        this.state.promotionFilters.status = status;
        this.state.promotionFilters.page = 1;
        await this.loadPromotions();
    }

    async applyPromotionFilters() {
        this.state.promotionFilters.page = 1;
        await this.loadPromotions();
    }

    async setCatalogType(type) {
        this.state.catalogFilters.type = type;
        this.state.catalogFilters.page = 1;
        await this.loadCatalogs();
    }

    async applyOrderFilters() {
        this.state.orderFilters.offset = 0;
        await Promise.all([this.loadOrders(), this.loadAnalytics()]);
    }

    async previousPromotionsPage() {
        this.state.promotionFilters.page = Math.max(
            Number(this.state.promotions.pagination.page || 1) - 1,
            1
        );
        await this.loadPromotions();
    }

    async nextPromotionsPage() {
        this.state.promotionFilters.page =
            Number(this.state.promotions.pagination.page || 1) + 1;
        await this.loadPromotions();
    }

    async previousCatalogsPage() {
        this.state.catalogFilters.page = Math.max(
            Number(this.state.catalogs.pagination.page || 1) - 1,
            1
        );
        await this.loadCatalogs();
    }

    async nextCatalogsPage() {
        this.state.catalogFilters.page =
            Number(this.state.catalogs.pagination.page || 1) + 1;
        await this.loadCatalogs();
    }

    async previousOrdersPage() {
        const limit = Number(this.state.orders.pagination.limit || 50);
        this.state.orderFilters.offset = Math.max(
            Number(this.state.orders.pagination.offset || 0) - limit,
            0
        );
        await this.loadOrders();
    }

    async nextOrdersPage() {
        const fallback = Number(this.state.orders.pagination.offset || 0) +
            Number(this.state.orders.pagination.limit || 50);
        this.state.orderFilters.offset = Number(
            this.state.orders.pagination.next_offset ?? fallback
        );
        await this.loadOrders();
    }

    get filteredPromotions() {
        const query = this.state.promotionFilters.search.trim().toLowerCase();
        if (!query) {
            return this.state.promotions.items;
        }
        return this.state.promotions.items.filter((promotion) =>
            [
                promotion.name,
                promotion.promotion_id,
                promotion.item_id,
                promotion.sku,
                promotion.category_id,
            ]
                .join(" ")
                .toLowerCase()
                .includes(query)
        );
    }

    get filteredCatalogs() {
        const query = this.state.catalogFilters.search.trim().toLowerCase();
        if (!query) {
            return this.state.catalogs.items;
        }
        return this.state.catalogs.items.filter((catalog) =>
            [catalog.name, catalog.promotion_id, catalog.status, catalog.type]
                .join(" ")
                .toLowerCase()
                .includes(query)
        );
    }

    get analyticsBars() {
        const series = this.state.analytics.series || [];
        const maxValue = Math.max(...series.map((point) => point.aporte_ml), 0);
        return series.map((point) => ({
            ...point,
            height: maxValue ? Math.max(6, Math.round((point.aporte_ml / maxValue) * 100)) : 6,
        }));
    }

    typeLabel(value) {
        return (
            {
                SMART: "SMART",
                DEAL: "DEAL",
                PRE_NEGOTIATED: "PRE_NEGOTIATED",
                preNegotiated: "PRE_NEGOTIATED",
            }[value] || value || "Sin tipo"
        );
    }

    statusLabel(value) {
        return (
            {
                ACTIVE: "Active",
                SYNCED: "Synced",
                DELETED: "Eliminada",
                FINISHED: "Finalizada",
                PENDING: "Pendiente",
                PAUSED: "Pausada",
                FAILED_SYNC: "Failed sync",
                FAILED_ACTIVATION: "Fallida act.",
                FAILED_DEACTIVATION: "Fallida desact.",
                started: "Started",
                paid: "Pagada",
                cancelled: "Cancelada",
            }[value] || value || "Sin estado"
        );
    }

    statusClass(value) {
        const normalized = String(value || "").toLowerCase();
        if (["active", "started", "paid", "synced"].includes(normalized)) {
            return "is-green";
        }
        if (["deleted", "cancelled", "failed_sync", "failed_activation"].includes(normalized)) {
            return "is-red";
        }
        if (["finished"].includes(normalized)) {
            return "is-gray";
        }
        return "is-blue";
    }

    formatNumber(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0";
        }
        return new Intl.NumberFormat("es-AR").format(numericValue);
    }

    formatCurrency(value, digits = 0) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "-";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: "ARS",
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(numericValue);
    }

    formatPercent(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "-";
        }
        return `${new Intl.NumberFormat("es-AR", {
            maximumFractionDigits: 2,
        }).format(numericValue)}%`;
    }

    formatDateTime(value) {
        if (!value) {
            return "-";
        }
        return new Intl.DateTimeFormat("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        }).format(new Date(value));
    }

    formatDate(value) {
        if (!value) {
            return "-";
        }
        return new Intl.DateTimeFormat("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "2-digit",
        }).format(new Date(value));
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.mercadolibre_promotions", LqaMercadolibrePromotions);
