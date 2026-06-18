/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LqaRetailersCatalog extends Component {
    static template = "lqa_admin_panel.RetailersCatalog";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            query: "",
            searchResult: null,
            catalog: {
                items: [],
                pagination: {},
            },
            filters: {
                offset: 0,
                limit: "10",
            },
            loadingCatalog: true,
            searching: false,
        });

        onWillStart(async () => {
            await this.loadCatalog();
        });
    }

    get showingSearch() {
        return this.state.searchResult !== null;
    }

    get displayedItems() {
        return this.showingSearch
            ? [this.state.searchResult]
            : this.state.catalog.items;
    }

    async loadCatalog() {
        this.state.loadingCatalog = true;
        try {
            this.state.catalog = await this.orm.call(
                "lqa.retailers.service",
                "get_marketplace_catalog",
                [{ ...this.state.filters }]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el catálogo.");
        } finally {
            this.state.loadingCatalog = false;
        }
    }

    async searchSku() {
        const sellerSku = this.state.query.trim();
        if (!sellerSku) {
            this.notification.add("Ingresá un seller SKU.", { type: "warning" });
            return;
        }
        this.state.searching = true;
        try {
            this.state.searchResult = await this.orm.call(
                "lqa.retailers.service",
                "get_marketplace_catalog_sku",
                [sellerSku]
            );
        } catch (error) {
            this.state.searchResult = null;
            this.notifyError(error, "No se pudo buscar el SKU.");
        } finally {
            this.state.searching = false;
        }
    }

    clearSearch() {
        this.state.query = "";
        this.state.searchResult = null;
    }

    async changeLimit() {
        this.state.filters.offset = 0;
        await this.loadCatalog();
    }

    async previousPage() {
        const limit = Number(this.state.catalog.pagination.limit || 10);
        this.state.filters.offset = Math.max(
            Number(this.state.catalog.pagination.offset || 0) - limit,
            0
        );
        await this.loadCatalog();
    }

    async nextPage() {
        this.state.filters.offset = Number(
            this.state.catalog.pagination.next_offset || 0
        );
        await this.loadCatalog();
    }

    async refreshCurrent() {
        if (this.showingSearch) {
            await this.searchSku();
            return;
        }
        await this.loadCatalog();
    }

    marketplaceLabel(value) {
        return (
            {
                fravega: "Fravega",
                megatone: "Megatone",
                oncity: "OnCity",
                "google-merchant": "Google Merchant",
            }[String(value || "").toLowerCase()] || value || "-"
        );
    }

    statusLabel(value) {
        return (
            {
                ACTIVE: "Activo",
                PAUSED: "Pausado",
                PENDING: "Pendiente",
                EN_REVISION: "En revisión",
                ERROR: "Error",
                SUCCESS: "Correcto",
                DELETED: "Eliminado",
            }[String(value || "").toUpperCase()] || value || "Sin estado"
        );
    }

    statusClass(value) {
        const normalized = String(value || "").toUpperCase();
        if (["ACTIVE", "SUCCESS"].includes(normalized)) {
            return "is-success";
        }
        if (["ERROR", "DELETED"].includes(normalized)) {
            return "is-error";
        }
        if (["PAUSED", "EN_REVISION", "PENDING"].includes(normalized)) {
            return "is-warning";
        }
        return "is-neutral";
    }

    formatNumber(value) {
        const numericValue = Number(value);
        return new Intl.NumberFormat("es-AR").format(
            Number.isFinite(numericValue) ? numericValue : 0
        );
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
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.retailers_catalog", LqaRetailersCatalog);
