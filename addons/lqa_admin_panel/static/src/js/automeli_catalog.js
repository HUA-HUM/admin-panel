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
            statusLoading: true,
            foldersLoading: true,
            savingSelection: false,
            products: [],
            pagination: {},
            catalogStatus: {
                total: 0,
                lastCreatedAt: "",
                lastUpdatedAt: "",
            },
            selectedProducts: {},
            folders: [],
            selectedFolderId: "",
            folderProducts: [],
            folderPagination: {},
            folderProductsLoading: false,
            newFolderName: "",
            filters: defaultFilters(),
        });

        onWillStart(async () => {
            await Promise.all([
                this.loadProducts(),
                this.loadCatalogStatus(),
                this.loadFolders(),
            ]);
        });
    }

    get selectedCount() {
        return Object.keys(this.state.selectedProducts || {}).length;
    }

    get selectedProductsList() {
        return Object.values(this.state.selectedProducts || {});
    }

    get selectedFolder() {
        return this.state.folders.find(
            (folder) => String(folder.id) === String(this.state.selectedFolderId)
        );
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

    async loadCatalogStatus() {
        this.state.statusLoading = true;
        try {
            this.state.catalogStatus = await this.orm.call(
                "lqa.automeli.catalog.service",
                "get_catalog_status",
                []
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo cargar el estado del catalogo Automeli.",
                { type: "warning" }
            );
        } finally {
            this.state.statusLoading = false;
        }
    }

    async loadFolders() {
        this.state.foldersLoading = true;
        try {
            this.state.folders = await this.orm.call(
                "lqa.automeli.catalog.service",
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
                "lqa.automeli.catalog.service",
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
                "lqa.automeli.catalog.service",
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
                "lqa.automeli.catalog.service",
                "get_selection_products",
                [Number(this.state.selectedFolderId)]
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
                "lqa.automeli.catalog.service",
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

    toggleProduct(product) {
        const key = this.productKey(product);
        if (!key) {
            return;
        }
        const selectedProducts = { ...this.state.selectedProducts };
        if (selectedProducts[key]) {
            delete selectedProducts[key];
        } else {
            selectedProducts[key] = product;
        }
        this.state.selectedProducts = selectedProducts;
    }

    selectVisibleProducts() {
        const selectedProducts = { ...this.state.selectedProducts };
        for (const product of this.state.products) {
            const key = this.productKey(product);
            if (key) {
                selectedProducts[key] = product;
            }
        }
        this.state.selectedProducts = selectedProducts;
    }

    clearSelection() {
        this.state.selectedProducts = {};
    }

    isSelected(product) {
        return Boolean(this.state.selectedProducts[this.productKey(product)]);
    }

    isFolderSelected(folder) {
        return String(folder.id) === String(this.state.selectedFolderId);
    }

    productKey(product) {
        return [product.mla, product.sku, product.listingTypeId]
            .filter(Boolean)
            .join("|");
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
