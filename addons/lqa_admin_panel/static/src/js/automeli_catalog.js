/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const defaultFilters = () => ({
    limit: "50",
    offset: 0,
    mla: "",
    sku: "",
    totalPrice: "",
    totalPriceMin: "",
    totalPriceMax: "",
    scrapedPrice: "",
    scrapedPriceMin: "",
    scrapedPriceMax: "",
    stockQuantity: "",
    stockQuantityMin: "",
    stockQuantityMax: "",
    amzStatus: "",
    changed: "",
    maxWeight: "",
    maxWeightMin: "",
    maxWeightMax: "",
    meliSalePrice: "",
    meliSalePriceMin: "",
    meliSalePriceMax: "",
    meliStatus: "",
    listingTypeId: "",
    subStatus: "",
    appStatus: "",
    createdAtFrom: "",
    createdAtTo: "",
    updatedAtFrom: "",
    updatedAtTo: "",
});

export class LqaAutomeliCatalog extends Component {
    static template = "lqa_admin_panel.AutomeliCatalog";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            products: [],
            pagination: {},
            filters: defaultFilters(),
        });

        onWillStart(async () => {
            await this.loadProducts();
        });
    }

    async loadProducts() {
        this.state.loading = true;
        try {
            const response = await this.orm.call(
                "lqa.automeli.catalog.service",
                "get_products",
                [{ ...this.state.filters }]
            );
            this.state.products = response.products;
            this.state.pagination = response.pagination;
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo cargar el catalogo Automeli.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async applyFilters() {
        this.state.filters.offset = 0;
        await this.loadProducts();
    }

    async clearFilters() {
        this.state.filters = defaultFilters();
        await this.loadProducts();
    }

    async previousPage() {
        const limit = Number(this.state.pagination.limit || 50);
        this.state.filters.offset = Math.max(
            Number(this.state.pagination.offset || 0) - limit,
            0
        );
        await this.loadProducts();
    }

    async nextPage() {
        const fallback = Number(this.state.pagination.offset || 0) +
            Number(this.state.pagination.limit || 50);
        this.state.filters.offset = Number(
            this.state.pagination.next_offset ?? fallback
        );
        await this.loadProducts();
    }

    formatCurrency(value, currency = "ARS", digits = 0) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "-";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency,
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(numericValue);
    }

    formatNumber(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0";
        }
        return new Intl.NumberFormat("es-AR").format(numericValue);
    }

    formatDateTime(value) {
        if (!value) {
            return "-";
        }
        return new Intl.DateTimeFormat("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(new Date(value));
    }

    meliStatusLabel(status) {
        return (
            {
                active: "Activa",
                paused: "Pausada",
                closed: "Cerrada",
                under_review: "En revision",
            }[status] || status || "Sin estado"
        );
    }

    appStatusLabel(status) {
        if (Number(status) === 1) {
            return "Habilitado";
        }
        if (Number(status) === 0) {
            return "Deshabilitado";
        }
        return "Sin estado";
    }

    listingLabel(listingType) {
        return (
            {
                gold_pro: "Premium",
                gold_special: "Clasica",
                free: "Gratuita",
            }[listingType] || listingType || "Sin tipo"
        );
    }

    productUrl(product) {
        return product.mla
            ? `https://articulo.mercadolibre.com.ar/${product.mla}`
            : false;
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.automeli_catalog", LqaAutomeliCatalog);
