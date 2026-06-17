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
            foldersLoading: true,
            savingSelection: false,
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

    async selectFolder(folderId) {
        this.state.selectedFolderId = String(folderId || "");
        await this.loadFolderProducts();
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
