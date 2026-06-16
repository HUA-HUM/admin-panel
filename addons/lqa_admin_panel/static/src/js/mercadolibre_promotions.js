/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
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
            loadingActions: false,
            runningAction: false,
            stats: { total: 0, cards: [] },
            promotions: { items: [], pagination: {} },
            catalogs: { items: [], summary: {}, pagination: {} },
            orders: { items: [], summary: {}, pagination: {} },
            analytics: { series: [], summary: {} },
            actionContext: {
                can_execute: false,
                updated_by: "",
                actions: [],
                history: [],
                datadog: {
                    base_url: "https://us5.datadoghq.com/logs/livetail",
                    service: "central-promos-enginee",
                },
            },
            actionForm: {
                updatedBy: "",
                promotionId: "",
            },
            pendingAction: null,
            datadogFilter: "",
            promotionFilters: defaultPromotionFilters(),
            catalogFilters: defaultCatalogFilters(),
            orderFilters: defaultOrderFilters(),
        });

        onMounted(() => {
            this.loadStats();
            this.loadPromotions();
        });

        onWillUnmount(() => {
            if (this.actionPollingTimer) {
                clearTimeout(this.actionPollingTimer);
            }
        });
    }

    async refreshCurrent() {
        await this.loadStats();
        if (this.state.activeTab === "central") {
            await this.loadPromotions();
        } else if (this.state.activeTab === "catalogs") {
            await this.loadCatalogs();
        } else if (this.state.activeTab === "orders") {
            await Promise.all([this.loadOrders(), this.loadAnalytics()]);
        } else if (this.state.activeTab === "actions") {
            await this.loadActionsContext();
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
        if (
            (tab === "actions" || tab === "datadog") &&
            !this.state.actionContext.actions.length
        ) {
            await this.loadActionsContext();
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

    async loadActionsContext() {
        this.state.loadingActions = true;
        try {
            const context = await this.orm.call(
                "lqa.mercadolibre.promotions.service",
                "get_actions_context",
                []
            );
            this.state.actionContext = context;
            if (!this.state.actionForm.updatedBy) {
                this.state.actionForm.updatedBy = context.updated_by || "";
            }
            this.scheduleActionPolling();
        } catch (error) {
            this.notifyError(error, "No se pudo cargar la seccion de acciones.");
        } finally {
            this.state.loadingActions = false;
        }
    }

    scheduleActionPolling() {
        if (this.actionPollingTimer) {
            clearTimeout(this.actionPollingTimer);
        }
        const hasRunning = (this.state.actionContext.history || []).some((log) =>
            ["queued", "running"].includes(log.status)
        );
        if (hasRunning) {
            this.actionPollingTimer = setTimeout(() => {
                this.loadActionsContext();
            }, 5000);
        }
    }

    openActionConfirmation(action) {
        if (!this.state.actionContext.can_execute) {
            this.notification.add("Solo administradores pueden ejecutar acciones.", {
                type: "warning",
            });
            return;
        }
        this.state.pendingAction = action;
    }

    closeActionConfirmation() {
        if (!this.state.runningAction) {
            this.state.pendingAction = null;
        }
    }

    async confirmAction() {
        const action = this.state.pendingAction;
        if (!action) {
            return;
        }
        if (action.requires_promotion_id && !this.state.actionForm.promotionId.trim()) {
            this.notification.add("Ingresa el promotionId antes de ejecutar.", {
                type: "warning",
            });
            return;
        }

        this.state.runningAction = true;
        try {
            await this.orm.call(
                "lqa.mercadolibre.promotions.service",
                "run_action",
                [
                    action.key,
                    {
                        updatedBy: this.state.actionForm.updatedBy,
                        promotionId: this.state.actionForm.promotionId,
                    },
                ]
            );
            this.notification.add("Proceso enviado al backend.", { type: "success" });
            this.state.pendingAction = null;
            await this.loadActionsContext();
        } catch (error) {
            this.notifyError(error, "No se pudo ejecutar la accion.");
        } finally {
            this.state.runningAction = false;
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

    get datadogUrl() {
        const datadog = this.state.actionContext.datadog || {};
        const params = new URLSearchParams({
            query: [
                `service:${datadog.service || "central-promos-enginee"}`,
                this.state.datadogFilter.trim(),
            ]
                .filter(Boolean)
                .join(" "),
            agg_m: "count",
            agg_m_source: "base",
            agg_t: "count",
            cols: "host,service",
            messageDisplay: "inline",
            refresh_mode: "sliding",
            storage: "driveline",
            stream_sort: "desc",
            viz: "stream",
            live: "true",
        });
        return `${datadog.base_url || "https://us5.datadoghq.com/logs/livetail"}?${params.toString()}`;
    }

    openDatadog() {
        window.open(this.datadogUrl, "_blank", "noopener,noreferrer");
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

    actionStatusLabel(status) {
        return (
            {
                queued: "En cola",
                running: "Ejecutando",
                completed: "Completado",
                failed: "Fallido",
            }[status] || status || "Sin estado"
        );
    }

    actionStatusClass(status) {
        return (
            {
                queued: "is-blue",
                running: "is-blue",
                completed: "is-green",
                failed: "is-red",
            }[status] || "is-gray"
        );
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
