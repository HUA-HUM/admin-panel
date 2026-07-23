/** @odoo-module **/

import { Component, onMounted, onWillUnmount, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MARKETPLACES = [
    {
        id: "oncity",
        name: "OnCity",
        subtitle: "Retail marketplace",
        description: "Productos publicados, imports y estados de publicaciones de OnCity.",
        accent: "oncity",
        logo: "/lqa_admin_panel/static/src/img/marketplace/oncity.png?v=1",
    },
    {
        id: "fravega",
        name: "Fravega",
        subtitle: "Retail marketplace",
        description: "Catalogo publicado, sincronizaciones y salud operativa de Fravega.",
        accent: "fravega",
        logo: "/lqa_admin_panel/static/src/img/marketplace/fravega.png?v=1",
    },
    {
        id: "google-merchant",
        name: "Google Merchant",
        subtitle: "Feed y Merchant Center",
        description: "Productos, imports y estado de publicaciones para Google Merchant.",
        accent: "google",
        logo: "/lqa_admin_panel/static/src/img/marketplace/google-merchant.png?v=1",
    },
    {
        id: "megatone",
        name: "Megatone",
        subtitle: "Retail marketplace",
        description: "Catalogo, stock, precios e importaciones asincronicas de Megatone.",
        accent: "megatone",
        logo: "/lqa_admin_panel/static/src/img/marketplace/megatone.svg?v=1",
    },
];

const ACTION_MARKETPLACES = MARKETPLACES.filter((marketplace) =>
    ["fravega", "megatone", "oncity"].includes(marketplace.id)
);

const GOOGLE_MERCHANT_DELETE_CONFIRMATION = "ELIMINAR TODO";

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
        this.pausedBulkFileInput = null;
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
            loadingPausedSkuRuns: false,
            loadingPausedSkus: false,
            runningImport: false,
            refreshingPublished: false,
            refreshingSku: false,
            refreshingBulk: false,
            upsertingPausedSku: false,
            upsertingPausedSkus: false,
            deletingPausedSku: "",
            confirmImport: false,
            confirmRefresh: false,
            confirmDeleteGoogleMerchant: false,
            deletingGoogleMerchantProducts: false,
            deletingGoogleMerchantProductKey: "",
            googleMerchantProductToDelete: null,
            googleMerchantDeleteConfirmation: "",
            dashboardOrders: emptyOrdersOverview(),
            dashboardError: "",
            bulkActionTab: "auto",
            refreshForm: {
                marketplace: "fravega",
                note: "",
            },
            refreshSkuForm: {
                marketplace: "fravega",
                sku: "",
                note: "",
            },
            refreshBulkForm: {
                marketplace: "fravega",
                runId: "",
                filename: "",
                content: "",
                note: "",
            },
            pausedSkuFilters: {
                sku: "",
                paused: "",
                offset: 0,
                limit: "100",
            },
            pausedSingleForm: {
                sku: "",
                paused: "true",
                note: "",
            },
            pausedBulkForm: {
                filename: "",
                content: "",
                defaultPaused: "true",
                note: "",
            },
            refreshResult: null,
            refreshSkuResult: null,
            refreshBulkResult: null,
            pausedSingleResult: null,
            pausedBulkResult: null,
            bulkActionRuns: [],
            pausedSkuRuns: [],
            pausedSkus: { items: [], pagination: {} },
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

    get selectedRefreshMarketplace() {
        return this.state.actionMarketplaces.find(
            (item) => item.id === this.state.refreshForm.marketplace
        );
    }

    get activeImportRun() {
        return (
            this.state.imports.items.find((run) => this.isImportRunActive(run)) ||
            null
        );
    }

    get canDeleteGoogleMerchantProduct() {
        return (
            Boolean(this.state.googleMerchantProductToDelete) &&
            !this.state.deletingGoogleMerchantProductKey
        );
    }

    get showDashboard() {
        return this.state.viewMode === "dashboard" && !this.state.marketplaceId;
    }

    get showMarketplaces() {
        return this.state.viewMode === "marketplaces" && !this.state.marketplaceId;
    }

    get showBulkActions() {
        return this.state.viewMode === "bulk_actions" && !this.state.marketplaceId;
    }

    get showMarketplaceDetail() {
        return this.state.viewMode === "marketplace" && Boolean(this.state.marketplaceId);
    }

    get isGoogleMerchantDetail() {
        return this.state.marketplaceId === "google-merchant";
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

    get bulkActionRunsAuto() {
        return (this.state.bulkActionRuns || []).filter((run) => run.action_type === "published");
    }

    get bulkActionRunsManual() {
        return (this.state.bulkActionRuns || []).filter((run) => run.action_type !== "published");
    }

    get canDeleteGoogleMerchantCatalog() {
        return (
            this.state.googleMerchantDeleteConfirmation.trim().toUpperCase() ===
                GOOGLE_MERCHANT_DELETE_CONFIRMATION &&
            !this.state.deletingGoogleMerchantProducts
        );
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
        this.state.confirmImport = false;
        this.state.confirmRefresh = false;
        this.state.confirmDeleteGoogleMerchant = false;
        this.state.googleMerchantDeleteConfirmation = "";
        if (marketplaceId) {
            this.resetMarketplaceDetail();
        }
        this.loadCurrentView();
    }

    loadCurrentView() {
        if (this.showDashboard) {
            this.loadDashboard();
        } else if (this.showBulkActions) {
            if (this.state.bulkActionTab === "paused") {
                this.loadPausedSkus();
                this.loadPausedSkuRuns();
            } else {
                this.loadBulkActionRuns();
            }
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
        this.state.confirmImport = false;
        this.state.confirmDeleteGoogleMerchant = false;
        this.state.googleMerchantDeleteConfirmation = "";
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

    openImportConfirmation() {
        this.state.confirmImport = true;
    }

    closeImportConfirmation() {
        if (!this.state.runningImport) {
            this.state.confirmImport = false;
        }
    }

    async confirmRunImport() {
        this.state.runningImport = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "run_import",
                [this.state.marketplaceId]
            );
            this.notification.add(
                `Import enviado: ${this.importStatusLabel(result.status)}`,
                { type: "success" }
            );
            this.state.confirmImport = false;
            this.state.activeTab = "imports";
            await this.loadImports();
        } catch (error) {
            this.notifyError(error, "No se pudo disparar el import.");
        } finally {
            this.state.runningImport = false;
        }
    }

    openRefreshConfirmation() {
        this.state.confirmRefresh = true;
    }

    closeRefreshConfirmation() {
        if (!this.state.refreshingPublished) {
            this.state.confirmRefresh = false;
        }
    }

    async confirmRefreshPublished() {
        this.state.refreshingPublished = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "refresh_published",
                [this.state.refreshForm.marketplace, this.state.refreshForm.note]
            );
            this.state.refreshResult = result;
            this.state.refreshForm.note = "";
            this.state.confirmRefresh = false;
            await this.loadBulkActionRuns();
            this.notification.add(
                `Actualizacion enviada para ${result.marketplace_name || this.marketplaceName(result.marketplace)}.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo disparar la actualizacion.");
        } finally {
            this.state.refreshingPublished = false;
        }
    }

    async setBulkActionTab(tab) {
        this.state.bulkActionTab = tab;
        if (tab === "paused") {
            await Promise.all([this.loadPausedSkus(), this.loadPausedSkuRuns()]);
        } else {
            await this.loadBulkActionRuns();
        }
    }

    async loadBulkActionRuns() {
        this.state.loadingBulkActionRuns = true;
        try {
            this.state.bulkActionRuns = await this.orm.call(
                "lqa.retailers.service",
                "get_bulk_action_runs",
                [30]
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar los registros de ejecucion.");
        } finally {
            this.state.loadingBulkActionRuns = false;
        }
    }

    async loadPausedSkuRuns() {
        this.state.loadingPausedSkuRuns = true;
        try {
            this.state.pausedSkuRuns = await this.orm.call(
                "lqa.retailers.service",
                "get_paused_sku_action_runs",
                [30]
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar los registros de SKUs pausados.");
        } finally {
            this.state.loadingPausedSkuRuns = false;
        }
    }

    async submitRefreshSku() {
        if (!this.state.refreshSkuForm.sku.trim()) {
            this.notification.add("Ingresa un SKU para actualizar.", {
                type: "warning",
            });
            return;
        }
        this.state.refreshingSku = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "refresh_published_sku",
                [
                    this.state.refreshSkuForm.marketplace,
                    this.state.refreshSkuForm.sku,
                    this.state.refreshSkuForm.note,
                ]
            );
            this.state.refreshSkuResult = result;
            this.state.refreshSkuForm.note = "";
            await this.loadBulkActionRuns();
            this.notification.add(
                `Actualizacion enviada para ${result.sku} en ${result.marketplace_name}.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo actualizar el SKU.");
        } finally {
            this.state.refreshingSku = false;
        }
    }

    async onRefreshBulkFileChange(event) {
        this.refreshBulkFileInput = event.target;
        const file = event.target.files?.[0];
        if (!file) {
            this.clearRefreshBulkFile();
            return;
        }
        try {
            const dataUrl = await this.readFileAsDataUrl(file);
            this.state.refreshBulkForm.filename = file.name;
            this.state.refreshBulkForm.content = dataUrl.split(",", 2)[1] || "";
        } catch (error) {
            this.clearRefreshBulkFile();
            this.notification.add("No se pudo leer el archivo seleccionado.", {
                type: "danger",
            });
        }
    }

    clearRefreshBulkFile() {
        this.state.refreshBulkForm.filename = "";
        this.state.refreshBulkForm.content = "";
        if (this.refreshBulkFileInput) {
            this.refreshBulkFileInput.value = "";
        }
    }

    async submitRefreshBulk() {
        if (!this.state.refreshBulkForm.content) {
            this.notification.add("Selecciona un CSV o Excel con SKUs.", {
                type: "warning",
            });
            return;
        }
        this.state.refreshingBulk = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "refresh_published_bulk",
                [
                    this.state.refreshBulkForm.marketplace,
                    this.state.refreshBulkForm.filename,
                    this.state.refreshBulkForm.content,
                    this.state.refreshBulkForm.runId,
                    this.state.refreshBulkForm.note,
                ]
            );
            this.state.refreshBulkResult = result;
            this.state.refreshBulkForm.note = "";
            this.clearRefreshBulkFile();
            await this.loadBulkActionRuns();
            this.notification.add(
                `Bulk enviado: ${this.formatNumber(result.sku_count)} SKUs para ${result.marketplace_name}.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo enviar el bulk de SKUs.");
        } finally {
            this.state.refreshingBulk = false;
        }
    }

    readFileAsDataUrl(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }

    async loadPausedSkus() {
        this.state.loadingPausedSkus = true;
        try {
            this.state.pausedSkus = await this.orm.call(
                "lqa.retailers.service",
                "get_paused_skus",
                [{ ...this.state.pausedSkuFilters }]
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar los SKUs pausados.");
        } finally {
            this.state.loadingPausedSkus = false;
        }
    }

    async applyPausedSkuFilters() {
        this.state.pausedSkuFilters.offset = 0;
        await this.loadPausedSkus();
    }

    clearPausedSkuFilters() {
        this.state.pausedSkuFilters.sku = "";
        this.state.pausedSkuFilters.paused = "";
        this.state.pausedSkuFilters.offset = 0;
        this.loadPausedSkus();
    }

    async previousPausedSkusPage() {
        const limit = Number(this.state.pausedSkus.pagination.limit || 100);
        this.state.pausedSkuFilters.offset = Math.max(
            Number(this.state.pausedSkus.pagination.offset || 0) - limit,
            0
        );
        await this.loadPausedSkus();
    }

    async nextPausedSkusPage() {
        this.state.pausedSkuFilters.offset = Number(
            this.state.pausedSkus.pagination.next_offset || 0
        );
        await this.loadPausedSkus();
    }

    async submitPausedSingle() {
        if (!this.state.pausedSingleForm.sku.trim()) {
            this.notification.add("Ingresa un SKU para guardar.", {
                type: "warning",
            });
            return;
        }
        this.state.upsertingPausedSku = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "upsert_paused_sku",
                [
                    this.state.pausedSingleForm.sku,
                    this.state.pausedSingleForm.paused === "true",
                    this.state.pausedSingleForm.note,
                ]
            );
            this.state.pausedSingleResult = result;
            this.state.pausedSingleForm.sku = "";
            this.state.pausedSingleForm.note = "";
            await Promise.all([this.loadPausedSkus(), this.loadPausedSkuRuns()]);
            this.notification.add(
                `${result.sku} guardado como ${this.pausedLabel(result.paused_count > 0)}.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo guardar el SKU pausado.");
        } finally {
            this.state.upsertingPausedSku = false;
        }
    }

    async deletePausedSku(item) {
        const sku = String(item?.sku || "").trim();
        if (!sku) {
            this.notification.add("No encontre SKU para eliminar.", {
                type: "warning",
            });
            return;
        }
        if (!window.confirm(`Eliminar ${sku} del listado de SKUs pausados?`)) {
            return;
        }
        this.state.deletingPausedSku = sku;
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "delete_paused_sku",
                [sku]
            );
            this.notification.add(
                result.message || `${result.sku || sku} eliminado del listado.`,
                { type: "success" }
            );
            await this.loadPausedSkus();
        } catch (error) {
            this.notifyError(error, "No se pudo eliminar el SKU pausado.");
        } finally {
            this.state.deletingPausedSku = "";
        }
    }

    async onPausedBulkFileChange(event) {
        this.pausedBulkFileInput = event.target;
        const file = event.target.files?.[0];
        if (!file) {
            this.clearPausedBulkFile();
            return;
        }
        try {
            const dataUrl = await this.readFileAsDataUrl(file);
            this.state.pausedBulkForm.filename = file.name;
            this.state.pausedBulkForm.content = dataUrl.split(",", 2)[1] || "";
        } catch (error) {
            this.clearPausedBulkFile();
            this.notification.add("No se pudo leer el archivo seleccionado.", {
                type: "danger",
            });
        }
    }

    clearPausedBulkFile() {
        this.state.pausedBulkForm.filename = "";
        this.state.pausedBulkForm.content = "";
        if (this.pausedBulkFileInput) {
            this.pausedBulkFileInput.value = "";
        }
    }

    async submitPausedBulk() {
        if (!this.state.pausedBulkForm.content) {
            this.notification.add("Selecciona un CSV o Excel con SKUs.", {
                type: "warning",
            });
            return;
        }
        this.state.upsertingPausedSkus = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.service",
                "upsert_paused_skus_bulk",
                [
                    this.state.pausedBulkForm.filename,
                    this.state.pausedBulkForm.content,
                    this.state.pausedBulkForm.defaultPaused === "true",
                    this.state.pausedBulkForm.note,
                ]
            );
            this.state.pausedBulkResult = result;
            this.state.pausedBulkForm.note = "";
            this.clearPausedBulkFile();
            await Promise.all([this.loadPausedSkus(), this.loadPausedSkuRuns()]);
            this.notification.add(
                `Bulk enviado: ${this.formatNumber(result.sku_count)} SKUs procesados.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo enviar el bulk de SKUs pausados.");
        } finally {
            this.state.upsertingPausedSkus = false;
        }
    }

    openGoogleMerchantDeleteConfirmation() {
        this.state.googleMerchantDeleteConfirmation = "";
        this.state.confirmDeleteGoogleMerchant = true;
    }

    closeGoogleMerchantDeleteConfirmation() {
        if (!this.state.deletingGoogleMerchantProducts) {
            this.state.confirmDeleteGoogleMerchant = false;
            this.state.googleMerchantDeleteConfirmation = "";
        }
    }

    onGoogleMerchantDeleteKeydown(event) {
        if (event.key === "Enter") {
            this.confirmDeleteGoogleMerchantCatalog();
        }
    }

    async confirmDeleteGoogleMerchantCatalog() {
        if (!this.canDeleteGoogleMerchantCatalog) {
            this.notification.add(
                `Escribi ${GOOGLE_MERCHANT_DELETE_CONFIRMATION} para confirmar.`,
                { type: "warning" }
            );
            return;
        }
        this.state.deletingGoogleMerchantProducts = true;
        try {
            const result = await this.orm.call(
                "lqa.google.merchant.actions.service",
                "delete_all_products",
                [this.state.googleMerchantDeleteConfirmation]
            );
            this.state.confirmDeleteGoogleMerchant = false;
            this.state.googleMerchantDeleteConfirmation = "";
            await this.loadProducts();
            this.notification.add(
                result.message ||
                    result.error_message ||
                    "La eliminacion total finalizo.",
                {
                    type:
                        result.status === "completed"
                            ? "success"
                            : result.status === "partial"
                            ? "warning"
                            : "danger",
                }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo eliminar el catalogo.");
        } finally {
            this.state.deletingGoogleMerchantProducts = false;
        }
    }

    openGoogleMerchantProductDelete(product) {
        if (!this.googleMerchantProductSku(product)) {
            this.notification.add(
                "No encontre el SKU / offer ID para eliminar este producto.",
                { type: "warning" }
            );
            return;
        }
        this.state.googleMerchantProductToDelete = product;
    }

    closeGoogleMerchantProductDelete() {
        if (!this.state.deletingGoogleMerchantProductKey) {
            this.state.googleMerchantProductToDelete = null;
        }
    }

    async confirmDeleteGoogleMerchantProduct() {
        const product = this.state.googleMerchantProductToDelete;
        const sku = this.googleMerchantProductSku(product);
        if (!product || !sku) {
            this.notification.add(
                "No encontre el SKU / offer ID para eliminar este producto.",
                { type: "warning" }
            );
            return;
        }
        const productKey = this.productCardKey(product);
        this.state.deletingGoogleMerchantProductKey = productKey;
        try {
            const result = await this.orm.call(
                "lqa.google.merchant.actions.service",
                "delete_selected_products",
                [
                    [
                        {
                            sku,
                            contentLanguage:
                                product.content_language || product.contentLanguage || "es",
                            feedLabel: product.feed_label || product.feedLabel || "AR",
                        },
                    ],
                ]
            );
            this.state.googleMerchantProductToDelete = null;
            await this.loadProducts();
            this.notification.add(
                result.message ||
                    result.error_message ||
                    `Producto ${sku} eliminado de Google Merchant.`,
                {
                    type:
                        result.status === "failed"
                            ? "danger"
                            : result.status === "partial"
                            ? "warning"
                            : "success",
                }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo eliminar el producto.");
        } finally {
            this.state.deletingGoogleMerchantProductKey = "";
        }
    }

    googleMerchantProductSku(product) {
        return String(
            product?.offer_id ||
                product?.google_product_key ||
                product?.external_id ||
                product?.sku ||
                ""
        ).trim();
    }

    isDeletingGoogleMerchantProduct(product) {
        return (
            this.state.deletingGoogleMerchantProductKey &&
            this.state.deletingGoogleMerchantProductKey === this.productCardKey(product)
        );
    }

    productCardKey(product) {
        return product?.card_key || product?.google_product_key || product?.id || product?.sku;
    }

    productCardClass(product) {
        return "o_lqa_product_card";
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

    bulkActionLabel(value) {
        return (
            {
                published: "Publicaciones",
                sku: "SKU puntual",
                bulk: "Archivo de SKUs",
                paused_single: "SKU pausado",
                paused_bulk: "Archivo pausados",
            }[String(value || "")] || "Accion"
        );
    }

    bulkActionIcon(value) {
        return (
            {
                published: "fa-refresh",
                sku: "fa-barcode",
                bulk: "fa-file-excel-o",
                paused_single: "fa-pause-circle-o",
                paused_bulk: "fa-cloud-upload",
            }[String(value || "")] || "fa-history"
        );
    }

    bulkActionDetail(run) {
        if (run?.sku) {
            return run.sku;
        }
        if (run?.filename) {
            const count = Number(run.sku_count || 0);
            return count > 0
                ? `${run.filename} · ${this.formatNumber(count)} SKUs`
                : run.filename;
        }
        return "Marketplace completo";
    }

    pausedLabel(value) {
        return value ? "Pausado" : "Activo";
    }

    pausedClass(value) {
        return value ? "is-red" : "is-green";
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

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }
}

registry.category("actions").add("lqa_admin_panel.retailers", LqaRetailers);
