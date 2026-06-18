/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const defaultProductFilters = () => ({
    page: 1,
    limit: "20",
    brand: "",
    categoryId: "",
    minPrice: "",
    maxPrice: "",
    minStock: "",
    maxStock: "",
    minVisits: "",
    maxVisits: "",
    minOrders: "",
    maxOrders: "",
    sortBy: "",
    sortOrder: "asc",
});

export class LqaRetailersPublisher extends Component {
    static template = "lqa_admin_panel.RetailersPublisher";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.fileInput = null;
        this.state = useState({
            folders: [],
            products: [],
            pagination: {},
            selectedFolderId: "",
            selectedProductIds: {},
            loadingFolders: true,
            loadingProducts: false,
            creatingFolder: false,
            addingManual: false,
            importingFile: false,
            deletingProducts: false,
            downloadingTemplate: false,
            confirmDelete: false,
            filtersOpen: false,
            filters: defaultProductFilters(),
            newFolderName: "",
            manual: {
                productId: "",
                sellerSku: "",
            },
            upload: {
                name: "",
                content: "",
            },
        });

        onWillStart(async () => {
            await this.loadFolders();
        });
    }

    get selectedFolder() {
        return this.state.folders.find(
            (folder) => String(folder.id) === String(this.state.selectedFolderId)
        );
    }

    get selectedProductIds() {
        return Object.keys(this.state.selectedProductIds).filter(
            (productId) => this.state.selectedProductIds[productId]
        );
    }

    get selectableProducts() {
        return this.state.products.filter((product) => product.delete_id);
    }

    get allCurrentProductsSelected() {
        return (
            this.selectableProducts.length > 0 &&
            this.selectableProducts.every(
                (product) => this.state.selectedProductIds[product.delete_id]
            )
        );
    }

    async loadFolders(preferredFolderId = this.state.selectedFolderId) {
        this.state.loadingFolders = true;
        try {
            const folders = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_folders",
                []
            );
            this.state.folders = folders || [];
            const preferredExists = this.state.folders.some(
                (folder) => String(folder.id) === String(preferredFolderId)
            );
            if (preferredExists) {
                this.state.selectedFolderId = String(preferredFolderId);
            } else if (this.state.folders.length) {
                this.state.selectedFolderId = String(this.state.folders[0].id);
            } else {
                this.state.selectedFolderId = "";
            }
            await this.loadFolderProducts();
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar las carpetas de Madre.");
        } finally {
            this.state.loadingFolders = false;
        }
    }

    async selectFolder(folder) {
        if (String(folder.id) === String(this.state.selectedFolderId)) {
            return;
        }
        this.state.selectedFolderId = String(folder.id);
        this.state.filters = defaultProductFilters();
        this.clearProductSelection();
        await this.loadFolderProducts();
    }

    async loadFolderProducts() {
        if (!this.selectedFolder) {
            this.state.products = [];
            this.state.pagination = {};
            return;
        }
        this.state.loadingProducts = true;
        try {
            const response = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_folder_products",
                [this.selectedFolder.id, { ...this.state.filters }]
            );
            this.state.products = response.products || [];
            this.state.pagination = response.pagination || {};
            this.state.filters.page = this.state.pagination.page || 1;
            this.selectedFolder.product_count = this.state.pagination.total || 0;
        } catch (error) {
            this.state.products = [];
            this.state.pagination = {};
            this.notifyError(error, "No se pudieron cargar los productos de la carpeta.");
        } finally {
            this.state.loadingProducts = false;
        }
    }

    async createFolder() {
        const name = this.state.newFolderName.trim();
        if (!name) {
            this.notification.add("Ingresa un nombre para la carpeta.", {
                type: "warning",
            });
            return;
        }
        this.state.creatingFolder = true;
        try {
            const created = await this.orm.call(
                "lqa.retailers.publisher.service",
                "create_folder",
                [name]
            );
            this.state.newFolderName = "";
            await this.loadFolders(created?.id || "");
            if (!created?.id) {
                const matchingFolder = this.state.folders.find(
                    (folder) => folder.name === name
                );
                if (matchingFolder) {
                    await this.selectFolder(matchingFolder);
                }
            }
            this.notification.add("Carpeta creada en Madre.", { type: "success" });
        } catch (error) {
            this.notifyError(error, "No se pudo crear la carpeta.");
        } finally {
            this.state.creatingFolder = false;
        }
    }

    async addManualProduct() {
        if (!this.selectedFolder) {
            this.notification.add("Selecciona una carpeta.", { type: "warning" });
            return;
        }
        const folderId = this.selectedFolder.id;
        const productId = this.state.manual.productId.trim();
        const sellerSku = this.state.manual.sellerSku.trim();
        if (!productId || !sellerSku) {
            this.notification.add("Completa productId y sellerSku.", {
                type: "warning",
            });
            return;
        }
        this.state.addingManual = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.publisher.service",
                "add_products",
                [folderId, [{ productId, sellerSku }]]
            );
            this.state.manual.productId = "";
            this.state.manual.sellerSku = "";
            this.state.filters.page = 1;
            await this.loadFolders(folderId);
            this.notification.add(
                `${this.formatNumber(result.count)} producto agregado a la carpeta.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo agregar el producto.");
        } finally {
            this.state.addingManual = false;
        }
    }

    async onFileChange(event) {
        const file = event.target.files?.[0];
        this.fileInput = event.target;
        if (!file) {
            this.clearUpload();
            return;
        }
        if (!file.name.toLowerCase().endsWith(".xlsx")) {
            this.clearUpload();
            this.notification.add("Selecciona un archivo de Excel XLSX.", {
                type: "warning",
            });
            return;
        }
        try {
            const dataUrl = await this.readFileAsDataUrl(file);
            this.state.upload.name = file.name;
            this.state.upload.content = dataUrl.split(",", 2)[1] || "";
        } catch {
            this.clearUpload();
            this.notification.add("No se pudo leer el archivo.", { type: "danger" });
        }
    }

    async importFile() {
        if (!this.selectedFolder) {
            this.notification.add("Selecciona una carpeta.", { type: "warning" });
            return;
        }
        if (!this.state.upload.content) {
            this.notification.add("Selecciona un archivo de Excel XLSX.", {
                type: "warning",
            });
            return;
        }
        const folderId = this.selectedFolder.id;
        this.state.importingFile = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.publisher.service",
                "import_products",
                [folderId, this.state.upload.name, this.state.upload.content]
            );
            this.clearUpload();
            this.state.filters.page = 1;
            await this.loadFolders(folderId);
            this.notification.add(
                `${this.formatNumber(result.count)} productos agregados en ${this.formatNumber(result.batches)} lote(s).`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo importar el archivo.");
        } finally {
            this.state.importingFile = false;
        }
    }

    async downloadTemplate() {
        this.state.downloadingTemplate = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.publisher.service",
                "download_import_template",
                []
            );
            this.downloadBase64File(result.filename, result.content, result.mimetype);
        } catch (error) {
            this.notifyError(error, "No se pudo descargar la plantilla de Excel.");
        } finally {
            this.state.downloadingTemplate = false;
        }
    }

    toggleFilters() {
        this.state.filtersOpen = !this.state.filtersOpen;
    }

    async applyProductFilters() {
        this.state.filters.page = 1;
        this.clearProductSelection();
        await this.loadFolderProducts();
    }

    async clearProductFilters() {
        this.state.filters = defaultProductFilters();
        this.clearProductSelection();
        await this.loadFolderProducts();
    }

    async previousProductsPage() {
        this.state.filters.page = Math.max(
            Number(this.state.pagination.page || 1) - 1,
            1
        );
        this.clearProductSelection();
        await this.loadFolderProducts();
    }

    async nextProductsPage() {
        this.state.filters.page = Number(this.state.pagination.page || 1) + 1;
        this.clearProductSelection();
        await this.loadFolderProducts();
    }

    toggleProduct(product) {
        if (!product.delete_id) {
            return;
        }
        this.state.selectedProductIds[product.delete_id] =
            !this.state.selectedProductIds[product.delete_id];
    }

    toggleCurrentPage() {
        const shouldSelect = !this.allCurrentProductsSelected;
        for (const product of this.selectableProducts) {
            this.state.selectedProductIds[product.delete_id] = shouldSelect;
        }
    }

    clearProductSelection() {
        this.state.selectedProductIds = {};
    }

    openDeleteConfirmation() {
        if (!this.selectedProductIds.length) {
            return;
        }
        this.state.confirmDelete = true;
    }

    closeDeleteConfirmation() {
        if (!this.state.deletingProducts) {
            this.state.confirmDelete = false;
        }
    }

    async confirmDeleteProducts() {
        if (!this.selectedFolder || !this.selectedProductIds.length) {
            return;
        }
        const folderId = this.selectedFolder.id;
        const productIds = [...this.selectedProductIds];
        this.state.deletingProducts = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.publisher.service",
                "delete_products",
                [folderId, productIds]
            );
            this.state.confirmDelete = false;
            this.clearProductSelection();
            await this.loadFolders(folderId);
            if (!this.state.products.length && this.state.filters.page > 1) {
                this.state.filters.page -= 1;
                await this.loadFolderProducts();
            }
            this.notification.add(
                `${this.formatNumber(result.count)} productos eliminados de la carpeta.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron eliminar los productos.");
        } finally {
            this.state.deletingProducts = false;
        }
    }

    clearUpload() {
        this.state.upload.name = "";
        this.state.upload.content = "";
        if (this.fileInput) {
            this.fileInput.value = "";
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

    downloadBase64File(filename, content, mimetype) {
        const binary = window.atob(content || "");
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index++) {
            bytes[index] = binary.charCodeAt(index);
        }
        const blob = new Blob([bytes], { type: mimetype });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename || "retailers-publicador-productos.xlsx";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    }

    isSelectedFolder(folder) {
        return String(folder.id) === String(this.state.selectedFolderId);
    }

    isProductSelected(product) {
        return Boolean(
            product.delete_id && this.state.selectedProductIds[product.delete_id]
        );
    }

    productUrl(product) {
        return product.product_id
            ? `https://articulo.mercadolibre.com.ar/${product.product_id}`
            : false;
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

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.retailers_publisher", LqaRetailersPublisher);
