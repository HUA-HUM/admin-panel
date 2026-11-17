/** @odoo-module **/

import { Component, onMounted, onWillUnmount, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MARKETPLACES = [
    {
        id: "fravega",
        name: "Fravega",
        subtitle: "Retail marketplace",
        description: "Catalogo publicado, sincronizaciones y salud operativa de Fravega.",
        accent: "fravega",
        logo: "/lqa_admin_panel/static/src/img/marketplace/fravega.png?v=1",
    },
];

const ACTION_MARKETPLACES = MARKETPLACES.filter((marketplace) =>
    ["fravega", "megatone", "oncity"].includes(marketplace.id)
);

const emptyOrdersOverview = () => ({
    mode: "last24",
    range: { from: "", to: "" },
    total: 0,
    marketplaces: [],
    items: [],
    errors: [],
});

const defaultProductFilters = () => ({
    offset: 0,
    limit: "10",
    sku: "",
    status: "",
});

const defaultImportFilters = () => ({
    offset: 0,
    limit: "20",
});

export class LqaRetailers extends Component {
    static template = "lqa_admin_panel.Retailers";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.refreshBulkFileInput = null;
        const params = this.props.action?.params || {};
        const initialMarketplaceId = params.marketplace_id || "";

        this.state = useState({
            viewMode: initialMarketplaceId ? "marketplace" : params.view || "dashboard",
            marketplaces: MARKETPLACES,
            actionMarketplaces: ACTION_MARKETPLACES,
            marketplaceId: initialMarketplaceId,
            activeTab: "products",
            loadingDashboard: false,
            loadingProducts: false,
            loadingImports: false,
            loadingStatus: false,
            loadingBulkActionRuns: false,
            downloadingMarketplaceSkus: false,
            productDetail: null,
            dashboardOrders: emptyOrdersOverview(),
            dashboardError: "",
            products: { items: [], summary: {}, pagination: {} },
            imports: { items: [], pagination: {} },
            status: { total: 0, statuses: [] },
            productFilters: defaultProductFilters(),
            importFilters: defaultImportFilters(),
        });

        onMounted(() => {
            this.loadCurrentView();
        });

        onWillUpdateProps((nextProps) => {
            this.applyActionParams(nextProps.action?.params || {});
        });

        onWillUnmount(() => {
            if (this.importPollingTimer) {
                clearTimeout(this.importPollingTimer);
            }
        });
    }

    get selectedMarketplace() {
        return this.state.marketplaces.find((item) => item.id === this.state.marketplaceId);
    }

    get activeImportRun() {
        return (
            this.state.imports.items.find((run) => this.isImportRunActive(run)) ||
            null
        );
    }

    get showDashboard() {
        return this.state.viewMode === "dashboard" && !this.state.marketplaceId;
    }

    get showMarketplaces() {
        return this.state.viewMode === "marketplaces" && !this.state.marketplaceId;
    }

    get showMarketplaceDetail() {
        return this.state.viewMode === "marketplace" && Boolean(this.state.marketplaceId);
    }

    get dashboardMarketplaceBreakdown() {
        const totals = new Map();
        for (const item of this.state.dashboardOrders.marketplaces || []) {
            const marketplace = String(item.marketplace || "").toLowerCase();
            if (marketplace) {
                totals.set(marketplace, Number(item.total || 0));
            }
        }
        return ACTION_MARKETPLACES.map((marketplace) => ({
            ...marketplace,
            total: totals.get(marketplace.id) || 0,
        }));
    }

    get dashboardErrorsCount() {
        return (this.state.dashboardOrders.errors || []).length;
    }

    get statusOptions() {
        const summary = this.state.products.summary || {};
        const statuses = Array.isArray(summary.statuses) ? summary.statuses : [];
        const options = statuses
            .map((item) => ({
                status: item.status,
                total: Number(item.total || 0),
                percentage: Number(item.percentage || 0),
            }))
            .filter((item) => item.status);
        if (
            this.state.productFilters.status &&
            !options.some((item) => item.status === this.state.productFilters.status)
        ) {
            options.unshift({
                status: this.state.productFilters.status,
                total: 0,
                percentage: 0,
            });
        }
        return options;
    }

    applyActionParams(params) {
        const marketplaceId = params.marketplace_id || "";
        const viewMode = marketplaceId ? "marketplace" : params.view || "dashboard";
        if (this.state.marketplaceId === marketplaceId && this.state.viewMode === viewMode) {
            return;
        }
        this.state.marketplaceId = marketplaceId;
        this.state.viewMode = viewMode;
        if (marketplaceId) {
            this.resetMarketplaceDetail();
        }
        this.loadCurrentView();
    }

    loadCurrentView() {
        if (this.showDashboard) {
            this.loadDashboard();
        } else if (this.showMarketplaceDetail) {
            this.loadCurrentTab();
        }
    }

    async loadDashboard() {
        this.state.loadingDashboard = true;
        this.state.dashboardError = "";
        try {
            this.state.dashboardOrders = await this.orm.call(
                "lqa.retailers.service",
                "get_orders_overview",
                ["last24", {}]
            );
        } catch (error) {
            this.state.dashboardOrders = emptyOrdersOverview();
            this.state.dashboardError =
                error?.data?.message || "No se pudo cargar el resumen de ordenes.";
        } finally {
            this.state.loadingDashboard = false;
        }
    }

    resetMarketplaceDetail() {
        this.state.activeTab = "products";
        this.state.productFilters = defaultProductFilters();
        this.state.importFilters = defaultImportFilters();
        this.state.products = { items: [], summary: {}, pagination: {} };
        this.state.imports = { items: [], pagination: {} };
        this.state.status = { total: 0, statuses: [] };
    }

    openMarketplace(marketplace) {
        this.state.viewMode = "marketplace";
        this.state.marketplaceId = marketplace.id;
        this.resetMarketplaceDetail();
        this.loadProducts();
    }

    backToMarketplaces() {
        this.state.viewMode = "marketplaces";
        this.state.marketplaceId = "";
        if (this.importPollingTimer) {
            clearTimeout(this.importPollingTimer);
        }
    }

    async refreshDashboard() {
        await this.loadDashboard();
    }

    async setTab(tab) {
        this.state.activeTab = tab;
        await this.loadCurrentTab();
    }

    async refreshCurrent() {
        if (!this.state.marketplaceId) {
            return;
        }
        await this.loadCurrentTab();
    }

    async loadCurrentTab() {
        if (this.state.activeTab === "products") {
            await this.loadProducts();
        } else if (this.state.activeTab === "imports") {
            await this.loadImports();
        } else if (this.state.activeTab === "status") {
            await this.loadStatus();
        }
    }

    async loadProducts() {
        if (!this.state.marketplaceId) {
            return;
        }
        this.state.loadingProducts = true;
        try {
            this.state.products = await this.orm.call(
                "lqa.retailers.service",
                "get_products",
                [this.state.marketplaceId, { ...this.state.productFilters }]
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar los productos.");
        } finally {
            this.state.loadingProducts = false;
        }
    }

    async loadImports() {
        if (!this.state.marketplaceId) {
            return;
        }
        this.state.loadingImports = true;
        try {
            this.state.imports = await this.orm.call(
                "lqa.retailers.service",
                "get_import_runs",
                [this.state.marketplaceId, { ...this.state.importFilters }]
            );
            this.scheduleImportPolling();
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el historial de imports.");
        } finally {
            this.state.loadingImports = false;
        }
    }

    async loadStatus() {
        if (!this.state.marketplaceId) {
            return;
        }
        this.state.loadingStatus = true;
        try {
            this.state.status = await this.orm.call(
                "lqa.retailers.service",
                "get_status",
                [this.state.marketplaceId]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el status del marketplace.");
        } finally {
            this.state.loadingStatus = false;
        }
    }

    scheduleImportPolling() {
        if (this.importPollingTimer) {
            clearTimeout(this.importPollingTimer);
        }
        if (this.state.activeTab !== "imports" || !this.state.marketplaceId) {
            return;
        }
        this.importPollingTimer = setTimeout(() => this.loadImports(), 10000);
    }

    async applyProductFilters() {
        this.state.productFilters.offset = 0;
        await this.loadProducts();
    }

    async setProductStatus(status) {
        this.state.productFilters.status = status;
        await this.applyProductFilters();
    }

    async previousProductsPage() {
        const limit = Number(this.state.products.pagination.limit || 10);
        this.state.productFilters.offset = Math.max(
            Number(this.state.products.pagination.offset || 0) - limit,
            0
        );
        await this.loadProducts();
    }

    async nextProductsPage() {
        this.state.productFilters.offset = Number(
            this.state.products.pagination.next_offset || 0
        );
        await this.loadProducts();
    }

    async downloadMarketplaceSkus() {
        if (!this.state.marketplaceId || this.state.downloadingMarketplaceSkus) {
            return;
        }
        this.state.downloadingMarketplaceSkus = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "download_marketplace_skus_xlsx",
                [this.state.marketplaceId]
            );
            this.downloadBase64File(
                result.filename,
                result.content,
                result.mimetype,
                "marketplace-catalogo-pricing.xlsx"
            );
            this.notification.add(
                `Excel generado con ${this.formatNumber(result.total || 0)} productos.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo descargar el Excel de SKUs.");
        } finally {
            this.state.downloadingMarketplaceSkus = false;
        }
    }

    async previousImportsPage() {
        const limit = Number(this.state.imports.pagination.limit || 20);
        this.state.importFilters.offset = Math.max(
            Number(this.state.imports.pagination.offset || 0) - limit,
            0
        );
        await this.loadImports();
    }

    async nextImportsPage() {
        this.state.importFilters.offset = Number(
            this.state.imports.pagination.next_offset || 0
        );
        await this.loadImports();
    }

    readFileAsDataUrl(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }

    productCardKey(product) {
        return product?.card_key || product?.google_product_key || product?.id || product?.sku;
    }

    productCardClass(product) {
        return "o_lqa_product_card";
    }

    openProductDetail(product) {
        this.state.productDetail = product;
    }

    closeProductDetail() {
        this.state.productDetail = null;
    }

    productDetailImages(product) {
        const images = product?.details?.images;
        if (Array.isArray(images) && images.length) {
            return images;
        }
        return product?.image ? [product.image] : [];
    }

    productDimensionsLabel(product) {
        const dimensions = product?.details?.dimensions || {};
        const parts = [dimensions.length, dimensions.width, dimensions.height]
            .filter((value) => Number.isFinite(Number(value)) && Number(value) > 0)
            .map((value) => this.formatNumber(value));
        if (!parts.length) {
            return "";
        }
        const size = `${parts.join(" x ")} cm`;
        if (Number.isFinite(Number(dimensions.weight)) && Number(dimensions.weight) > 0) {
            return `${size} · ${this.formatNumber(dimensions.weight)} kg`;
        }
        return size;
    }

    hasProductListPrice(product) {
        return Number.isFinite(Number(product?.list_price));
    }

    hasProductSalePrice(product) {
        return Number.isFinite(Number(product?.sale_price ?? product?.price));
    }

    productSalePrice(product) {
        return product?.sale_price ?? product?.price;
    }

    marketplaceName(value) {
        const marketplace = MARKETPLACES.find((item) => item.id === value);
        return marketplace?.name || this.humanizeStatus(value);
    }

    statusLabel(value) {
        return (
            {
                ACTIVE: "Activo",
                ERROR: "Error",
                EN_REVISION: "En revision",
                PAUSED: "Pausado",
                PENDING: "Pendiente",
                DELETED: "Eliminado",
                QUEUED: "En cola",
                STARTED: "Iniciado",
                RUNNING: "En progreso",
                SUCCESS: "Correcto",
                FAILED: "Fallido",
                UPDATED: "Actualizado",
            }[String(value || "").toUpperCase()] || this.humanizeStatus(value)
        );
    }

    statusClass(value) {
        const normalized = String(value || "").toUpperCase();
        if (["ACTIVE", "SUCCESS"].includes(normalized)) {
            return "is-green";
        }
        if (["ERROR", "FAILED"].includes(normalized)) {
            return "is-red";
        }
        if (["QUEUED", "STARTED", "RUNNING", "PENDING", "EN_REVISION", "UPDATED"].includes(normalized)) {
            return "is-blue";
        }
        return "is-gray";
    }

    importStatusLabel(value) {
        return this.statusLabel(value);
    }

    isImportRunActive(run) {
        return ["QUEUED", "STARTED", "RUNNING", "PENDING"].includes(
            String(run?.status || "").toUpperCase()
        );
    }

    importRunProgressCaption(run) {
        const processed = Number(run?.processed || run?.items_processed || 0);
        const total = Number(run?.total || 0);
        if (Number.isFinite(total) && total > 0) {
            return `${this.formatNumber(processed)} de ${this.formatNumber(total)} items`;
        }
        return `${this.formatNumber(processed)} items procesados`;
    }

    importRunProgressPercent(run) {
        const progress = Number(run?.progress);
        if (Number.isFinite(progress)) {
            return Math.max(0, Math.min(100, progress));
        }
        const processed = Number(run?.processed || run?.items_processed || 0);
        const total = Number(run?.total || 0);
        if (Number.isFinite(total) && total > 0) {
            return Math.max(0, Math.min(100, (processed / total) * 100));
        }
        return 0;
    }

    humanizeStatus(value) {
        const cleanValue = String(value || "").trim();
        if (!cleanValue) {
            return "Sin estado";
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

    downloadBase64File(filename, content, mimetype, fallbackFilename) {
        const binary = window.atob(content || "");
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index++) {
            bytes[index] = binary.charCodeAt(index);
        }
        const blob = new Blob([bytes], { type: mimetype || "application/octet-stream" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename || fallbackFilename || "descarga.xlsx";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    }

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }
}

registry.category("actions").add("lqa_admin_panel.retailers", LqaRetailers);
