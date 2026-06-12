/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const defaultFilters = () => ({
    search: "",
    brand: "",
    categoryId: "",
    domainId: "",
    status: "",
    condition: "",
    skuPrefix: "",
    hasOrders: "",
    hasVisits: "",
    minOrders: "",
    minRevenue: "",
    createdFrom: "",
    createdTo: "",
    sortBy: "revenue",
    sortOrder: "desc",
    limit: "100",
    offset: 0,
});

export class LqaMercadolibreCatalog extends Component {
    static template = "lqa_admin_panel.MercadolibreCatalog";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            products: [],
            pagination: {},
            sort: {},
            filters: defaultFilters(),
            selectedIds: {},
            showDeleteConfirmation: false,
            deleting: false,
            appKey: "default",
        });

        onWillStart(async () => {
            await this.loadProducts();
        });
    }

    async loadProducts() {
        this.state.loading = true;
        try {
            const response = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_products",
                [{ ...this.state.filters }]
            );
            this.state.products = response.products;
            this.state.pagination = response.pagination;
            this.state.sort = response.sort;
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo cargar el catalogo MercadoLibre.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async applyFilters() {
        this.clearSelection();
        this.state.filters.offset = 0;
        await this.loadProducts();
    }

    async clearFilters() {
        this.clearSelection();
        this.state.filters = defaultFilters();
        await this.loadProducts();
    }

    async previousPage() {
        const limit = Number(this.state.pagination.limit || this.state.filters.limit);
        this.state.filters.offset = Math.max(
            Number(this.state.pagination.offset || 0) - limit,
            0
        );
        await this.loadProducts();
    }

    async nextPage() {
        const limit = Number(this.state.pagination.limit || this.state.filters.limit);
        this.state.filters.offset =
            Number(this.state.pagination.offset || 0) + limit;
        await this.loadProducts();
    }

    formatCurrency(value, currency = "ARS") {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "-";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: currency || "ARS",
            maximumFractionDigits: 0,
        }).format(numericValue);
    }

    formatNumber(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0";
        }
        return new Intl.NumberFormat("es-AR").format(numericValue);
    }

    formatPercent(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0%";
        }
        return `${new Intl.NumberFormat("es-AR", {
            maximumFractionDigits: 2,
        }).format(numericValue)}%`;
    }

    formatDate(value) {
        if (!value) {
            return "-";
        }
        return new Intl.DateTimeFormat("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        }).format(new Date(value));
    }

    statusLabel(status) {
        return (
            {
                active: "Activa",
                paused: "Pausada",
                closed: "Cerrada",
            }[status] || status || "Sin estado"
        );
    }

    get selectedCount() {
        return Object.keys(this.state.selectedIds).length;
    }

    isSelected(itemId) {
        return Boolean(this.state.selectedIds[itemId]);
    }

    toggleProductSelection(event, itemId) {
        if (event.target.checked) {
            this.state.selectedIds[itemId] = true;
        } else {
            delete this.state.selectedIds[itemId];
        }
    }

    selectCurrentPage() {
        for (const product of this.state.products) {
            this.state.selectedIds[product.item_id] = true;
        }
    }

    clearSelection() {
        this.state.selectedIds = {};
    }

    openDeleteConfirmation() {
        if (!this.selectedCount) {
            this.notification.add("Selecciona al menos una publicacion.", {
                type: "warning",
            });
            return;
        }
        this.state.showDeleteConfirmation = true;
    }

    closeDeleteConfirmation() {
        if (!this.state.deleting) {
            this.state.showDeleteConfirmation = false;
        }
    }

    async confirmSelectedDeletion() {
        this.state.deleting = true;
        try {
            const result = await this.orm.call(
                "lqa.mercadolibre.deletion.service",
                "delete_products",
                [Object.keys(this.state.selectedIds), this.state.appKey]
            );
            this.notification.add(result.message, {
                type: result.ok ? "success" : "danger",
            });
            this.state.showDeleteConfirmation = false;
            if (result.deleted_count) {
                this.clearSelection();
                await this.loadProducts();
            }
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo ejecutar la eliminacion.",
                { type: "danger" }
            );
        } finally {
            this.state.deleting = false;
        }
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.mercadolibre_catalog", LqaMercadolibreCatalog);
