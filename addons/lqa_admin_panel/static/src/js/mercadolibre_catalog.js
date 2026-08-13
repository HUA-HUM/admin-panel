/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const defaultFilters = () => ({
    search: "",
    brand: "",
    categoryId: "",
    domainId: "",
    status: "",
    condition: "",
    listingTypeId: "",
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

const MAX_FOLDER_PRODUCTS = 500000;

export class LqaMercadolibreCatalog extends Component {
    static template = "lqa_admin_panel.MercadolibreCatalog";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            foldersLoading: true,
            savingSelection: false,
            savingFilteredSelection: false,
            selectionJob: null,
            products: [],
            pagination: {},
            sort: {},
            filters: defaultFilters(),
            selectedIds: {},
            folders: [],
            selectedFolderId: "",
            folderProducts: [],
            folderPagination: {},
            folderProductsLoading: false,
            newFolderName: "",
            showDeleteConfirmation: false,
            deleting: false,
            appKey: "default",
        });

        onWillStart(async () => {
            await Promise.all([this.loadProducts(), this.loadFolders()]);
            await this.loadActiveSelectionJob();
        });

        onWillUnmount(() => {
            if (this.selectionJobTimer) {
                clearTimeout(this.selectionJobTimer);
            }
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

    async loadFolders() {
        this.state.foldersLoading = true;
        try {
            this.state.folders = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_selection_folders",
                []
            );
            if (!this.state.selectedFolderId && this.state.folders.length) {
                this.state.selectedFolderId = String(this.state.folders[0].id);
                await this.loadFolderProducts();
            }
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudieron cargar las carpetas.",
                { type: "danger" }
            );
        } finally {
            this.state.foldersLoading = false;
        }
    }

    async loadActiveSelectionJob() {
        try {
            const job = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_active_selection_job",
                []
            );
            if (job) {
                this.state.selectionJob = job;
                this.state.selectedFolderId = String(job.folderId || "");
                this.updateSelectionFolderProgress(job);
                this.scheduleSelectionJobPolling();
            }
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo recuperar el guardado en curso.",
                { type: "warning" }
            );
        }
    }

    async createFolder() {
        const name = String(this.state.newFolderName || "").trim();
        if (!name) {
            this.notification.add("Indica un nombre para la carpeta.", {
                type: "warning",
            });
            return;
        }
        try {
            const folder = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "create_selection_folder",
                [name]
            );
            this.state.newFolderName = "";
            this.state.selectedFolderId = String(folder.id);
            await this.loadFolders();
            await this.loadFolderProducts();
            this.notification.add("Carpeta creada.", { type: "success" });
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo crear la carpeta.",
                { type: "danger" }
            );
        }
    }

    async saveSelectionToFolder() {
        if (!this.selectedCount) {
            this.notification.add("Selecciona productos del catalogo.", {
                type: "warning",
            });
            return;
        }
        if (!this.state.selectedFolderId) {
            this.notification.add("Crea o elegi una carpeta.", { type: "warning" });
            return;
        }
        this.state.savingSelection = true;
        try {
            const result = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "save_products_to_folder",
                [Number(this.state.selectedFolderId), this.selectedProductsList]
            );
            await this.loadFolders();
            await this.loadFolderProducts();
            this.clearSelection();
            this.notification.add(
                `Seleccion guardada: ${result.added} nuevos, ${result.updated} actualizados.`,
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo guardar la seleccion.",
                { type: "danger" }
            );
        } finally {
            this.state.savingSelection = false;
        }
    }

    async saveFilteredSelectionToFolder() {
        if (!this.state.selectedFolderId) {
            this.notification.add("Crea o elegi una carpeta.", { type: "warning" });
            return;
        }
        const total = Number(this.state.pagination.total || 0);
        if (!total) {
            this.notification.add("El filtro actual no tiene productos.", {
                type: "warning",
            });
            return;
        }
        if (total > MAX_FOLDER_PRODUCTS) {
            this.notification.add(
                `El filtro tiene ${this.formatNumber(total)} productos. El maximo por carpeta es ${this.formatNumber(MAX_FOLDER_PRODUCTS)}; refina el filtro antes de guardarlo.`,
                { type: "warning" }
            );
            return;
        }
        if (
            !window.confirm(
                `Vas a guardar todos los productos del filtro actual (${this.formatNumber(total)}) en la carpeta seleccionada.`
            )
        ) {
            return;
        }
        this.state.savingFilteredSelection = true;
        try {
            const job = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "save_filtered_products_to_folder",
                [Number(this.state.selectedFolderId), { ...this.state.filters }]
            );
            this.state.selectionJob = job;
            this.updateSelectionFolderProgress(job);
            this.notification.add(
                "El guardado masivo fue enviado y continuara en segundo plano.",
                { type: "info" }
            );
            this.scheduleSelectionJobPolling();
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo guardar todo el filtro.",
                { type: "danger" }
            );
        } finally {
            this.state.savingFilteredSelection = false;
        }
    }

    scheduleSelectionJobPolling() {
        if (this.selectionJobTimer) {
            clearTimeout(this.selectionJobTimer);
        }
        if (!this.isSelectionJobRunning) {
            return;
        }
        this.selectionJobTimer = setTimeout(() => this.pollSelectionJob(), 2500);
    }

    async pollSelectionJob() {
        const jobId = this.state.selectionJob?.id;
        if (!jobId) {
            return;
        }
        try {
            const job = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_selection_job",
                [jobId]
            );
            this.state.selectionJob = job;
            this.updateSelectionFolderProgress(job);
            const now = Date.now();
            if (
                ["queued", "running"].includes(job.state) &&
                String(job.folderId) === String(this.state.selectedFolderId) &&
                (!this.lastFolderProgressRefresh ||
                    now - this.lastFolderProgressRefresh >= 10000)
            ) {
                this.lastFolderProgressRefresh = now;
                await this.loadFolderProducts();
            }
            if (job.state === "done") {
                await Promise.all([this.loadFolders(), this.loadFolderProducts()]);
                this.clearSelection();
                this.notification.add(
                    `Filtro guardado: ${this.formatNumber(job.added)} nuevos y ${this.formatNumber(job.updated)} actualizados.`,
                    { type: "success" }
                );
            } else if (job.state === "failed") {
                this.notification.add(job.error || "El guardado masivo fallo.", {
                    type: "danger",
                });
            }
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo consultar el progreso del guardado.",
                { type: "danger" }
            );
        } finally {
            this.scheduleSelectionJobPolling();
        }
    }

    async retrySelectionJob() {
        const jobId = this.state.selectionJob?.id;
        if (!jobId || this.state.selectionJob?.state !== "failed") {
            return;
        }
        try {
            this.state.selectionJob = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "retry_selection_job",
                [jobId]
            );
            this.updateSelectionFolderProgress(this.state.selectionJob);
            this.notification.add("El proceso se retomara desde el ultimo lote guardado.", {
                type: "info",
            });
            this.scheduleSelectionJobPolling();
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo reintentar el guardado.",
                { type: "danger" }
            );
        }
    }

    async selectFolder(folderId) {
        this.state.selectedFolderId = String(folderId || "");
        await this.loadFolderProducts();
    }

    updateSelectionFolderProgress(job) {
        const folderId = String(job?.folderId || "");
        const folderCount = Number(job?.folderCount);
        if (!folderId || !Number.isFinite(folderCount)) {
            return;
        }
        this.state.folders = this.state.folders.map((folder) =>
            String(folder.id) === folderId
                ? { ...folder, productCount: folderCount }
                : folder
        );
        if (String(this.state.selectedFolderId) === folderId) {
            this.state.folderPagination = {
                ...this.state.folderPagination,
                total: folderCount,
            };
        }
    }

    async loadFolderProducts() {
        if (!this.state.selectedFolderId) {
            this.state.folderProducts = [];
            this.state.folderPagination = {};
            return;
        }
        this.state.folderProductsLoading = true;
        try {
            const response = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_selection_products",
                [Number(this.state.selectedFolderId), 200, 0]
            );
            this.state.folderProducts = response.products || [];
            this.state.folderPagination = response.pagination || {};
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudieron cargar los productos guardados.",
                { type: "danger" }
            );
        } finally {
            this.state.folderProductsLoading = false;
        }
    }

    async removeSavedProduct(product) {
        try {
            await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "remove_selection_product",
                [product.id]
            );
            await this.loadFolders();
            await this.loadFolderProducts();
            this.notification.add("Producto quitado de la carpeta.", { type: "success" });
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo quitar el producto.",
                { type: "danger" }
            );
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

    get selectedProductsList() {
        return Object.values(this.state.selectedIds || {});
    }

    get selectedMlaIds() {
        return this.selectedProductsList
            .map((product) => product.item_id || product.itemId)
            .filter(Boolean);
    }

    get selectedFolder() {
        return this.state.folders.find(
            (folder) => String(folder.id) === String(this.state.selectedFolderId)
        );
    }

    get isSelectionJobRunning() {
        return ["queued", "running"].includes(this.state.selectionJob?.state);
    }

    get selectionJobProgress() {
        const processed = Number(this.state.selectionJob?.processed || 0);
        const matched = Number(this.state.selectionJob?.matched || 0);
        if (!matched) {
            return 0;
        }
        return Math.min(Math.round((processed / matched) * 100), 100);
    }

    get filterExceedsFolderLimit() {
        return Number(this.state.pagination.total || 0) > MAX_FOLDER_PRODUCTS;
    }

    get maxFolderProducts() {
        return MAX_FOLDER_PRODUCTS;
    }

    isSelected(itemId) {
        return Boolean(this.state.selectedIds[itemId]);
    }

    toggleProductSelection(event, product) {
        const itemId = this.productKey(product);
        if (!itemId) {
            return;
        }
        const selectedIds = { ...this.state.selectedIds };
        if (event.target.checked) {
            selectedIds[itemId] = product;
        } else {
            delete selectedIds[itemId];
        }
        this.state.selectedIds = selectedIds;
    }

    selectCurrentPage() {
        const selectedIds = { ...this.state.selectedIds };
        for (const product of this.state.products) {
            const itemId = this.productKey(product);
            if (itemId) {
                selectedIds[itemId] = product;
            }
        }
        this.state.selectedIds = selectedIds;
    }

    clearSelection() {
        this.state.selectedIds = {};
    }

    isFolderSelected(folder) {
        return String(folder.id) === String(this.state.selectedFolderId);
    }

    productKey(product) {
        return product?.item_id || product?.itemId || product?.sku || product?.permalink || "";
    }

    openDeleteConfirmation() {
        if (!this.selectedCount) {
            this.notification.add("Selecciona al menos una publicacion.", {
                type: "warning",
            });
            return;
        }
        if (!this.selectedMlaIds.length) {
            this.notification.add("La seleccion no tiene IDs MLA validos.", {
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
                [this.selectedMlaIds, this.state.appKey]
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
