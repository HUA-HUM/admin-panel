/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const CSV_COLUMNS = [
    { key: "item_id", label: "MLA" },
    { key: "title", label: "Titulo" },
    { key: "sku", label: "SKU" },
    { key: "brand", label: "Marca" },
    { key: "status", label: "Estado" },
    { key: "condition", label: "Condicion" },
    { key: "listing_type_id", label: "Tipo publicacion" },
    { key: "price", label: "Precio" },
    { key: "currency_id", label: "Moneda" },
    { key: "available_quantity", label: "Stock" },
    { key: "revenue", label: "Facturacion" },
    { key: "orders_count", label: "Ordenes" },
    { key: "units_sold", label: "Unidades vendidas" },
    { key: "total_visits", label: "Visitas" },
    { key: "order_conversion_rate", label: "Conversion ordenes" },
    { key: "category_id", label: "Categoria" },
    { key: "domain_id", label: "Dominio" },
    { key: "permalink", label: "Link publicacion" },
    { key: "date_created", label: "Fecha creacion" },
    { key: "last_updated", label: "Ultima actualizacion" },
    { key: "catalog_sold_quantity", label: "Ventas catalogo" },
    { key: "avg_ticket", label: "Ticket promedio" },
    { key: "first_order_date", label: "Primera orden" },
    { key: "last_order_date", label: "Ultima orden" },
    { key: "unit_conversion_rate", label: "Conversion unidades" },
];

const DEFAULT_COLUMNS = [
    "item_id",
    "title",
    "sku",
    "status",
    "listing_type_id",
    "price",
    "available_quantity",
    "category_id",
    "permalink",
];

const defaultSelectedColumns = () =>
    Object.fromEntries(DEFAULT_COLUMNS.map((key) => [key, true]));

export class LqaMercadolibreSelections extends Component {
    static template = "lqa_admin_panel.MercadolibreSelections";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.importTimer = null;
        this.state = useState({
            folders: [],
            products: [],
            folderPagination: {},
            selectedFolderId: "",
            loadingFolders: true,
            loadingProducts: false,
            exportingFolderId: "",
            deletingFolder: null,
            selectedColumns: defaultSelectedColumns(),
            showImportModal: false,
            importFolderName: "",
            importFilename: "",
            importContent: "",
            importingFile: false,
            importJob: null,
        });

        onWillStart(async () => {
            await Promise.all([this.loadFolders(), this.loadInitialImportJob()]);
        });
        onMounted(() => {
            this.importTimer = window.setInterval(() => this.refreshImportJob(), 5000);
        });
        onWillUnmount(() => {
            if (this.importTimer) {
                window.clearInterval(this.importTimer);
            }
        });
    }

    get csvColumns() {
        return CSV_COLUMNS;
    }

    get selectedFolder() {
        return this.state.folders.find(
            (folder) => String(folder.id) === String(this.state.selectedFolderId)
        );
    }

    get selectedColumnKeys() {
        return CSV_COLUMNS.filter(
            (column) => this.state.selectedColumns[column.key]
        ).map((column) => column.key);
    }

    get selectedColumnCount() {
        return this.selectedColumnKeys.length;
    }

    async loadInitialImportJob() {
        try {
            const job = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_latest_mla_file_job",
                []
            );
            this.state.importJob = job || null;
        } catch {
            this.state.importJob = null;
        }
    }

    async loadFolders() {
        this.state.loadingFolders = true;
        try {
            this.state.folders = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_selection_folders",
                []
            );
            if (
                this.state.selectedFolderId &&
                !this.state.folders.some(
                    (folder) => String(folder.id) === String(this.state.selectedFolderId)
                )
            ) {
                this.state.selectedFolderId = "";
            }
            if (!this.state.selectedFolderId && this.state.folders.length) {
                this.state.selectedFolderId = String(this.state.folders[0].id);
            }
            await this.loadSelectedFolderProducts();
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudieron cargar las carpetas.",
                { type: "danger" }
            );
        } finally {
            this.state.loadingFolders = false;
        }
    }

    async selectFolder(folder) {
        this.state.selectedFolderId = String(folder.id);
        await this.loadSelectedFolderProducts();
    }

    async loadSelectedFolderProducts() {
        if (!this.state.selectedFolderId) {
            this.state.products = [];
            this.state.folderPagination = {};
            return;
        }
        this.state.loadingProducts = true;
        try {
            const response = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_selection_products",
                [Number(this.state.selectedFolderId), 1000, 0]
            );
            this.state.products = response.products || [];
            this.state.folderPagination = response.pagination || {};
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudieron cargar los productos de la carpeta.",
                { type: "danger" }
            );
        } finally {
            this.state.loadingProducts = false;
        }
    }

    toggleColumn(columnKey) {
        this.state.selectedColumns = {
            ...this.state.selectedColumns,
            [columnKey]: !this.state.selectedColumns[columnKey],
        };
    }

    selectAllColumns() {
        this.state.selectedColumns = Object.fromEntries(
            CSV_COLUMNS.map((column) => [column.key, true])
        );
    }

    selectDefaultColumns() {
        this.state.selectedColumns = defaultSelectedColumns();
    }

    clearColumns() {
        this.state.selectedColumns = {};
    }

    openImportModal() {
        this.state.showImportModal = true;
    }

    closeImportModal() {
        if (this.state.importingFile) {
            return;
        }
        this.state.showImportModal = false;
    }

    async onImportFileSelected(event) {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (!file) {
            return;
        }
        const extension = file.name.split(".").pop()?.toLowerCase();
        if (!["csv", "xlsx"].includes(extension)) {
            this.notification.add("El archivo debe ser CSV o XLSX.", { type: "warning" });
            return;
        }
        if (file.size > 20 * 1024 * 1024) {
            this.notification.add("El archivo puede pesar como máximo 20 MB.", { type: "warning" });
            return;
        }
        this.state.importFilename = file.name;
        this.state.importContent = await this.fileToBase64(file);
        if (!this.state.importFolderName) {
            this.state.importFolderName = file.name.replace(/\.(csv|xlsx)$/i, "");
        }
    }

    fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || "").split(",")[1] || "");
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    clearImportFile() {
        this.state.importFilename = "";
        this.state.importContent = "";
    }

    async submitMlaImport() {
        if (!String(this.state.importFolderName || "").trim()) {
            this.notification.add("Ingresá un nombre para la carpeta.", { type: "warning" });
            return;
        }
        if (!this.state.importContent) {
            this.notification.add("Seleccioná un archivo CSV o XLSX.", { type: "warning" });
            return;
        }
        this.state.importingFile = true;
        try {
            const result = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "import_mla_file_to_folder",
                [
                    this.state.importFolderName,
                    this.state.importFilename,
                    this.state.importContent,
                ]
            );
            this.state.importJob = result.job;
            this.state.selectedFolderId = String(result.folder.id);
            this.state.showImportModal = false;
            this.state.importFolderName = "";
            this.clearImportFile();
            await this.loadFolders();
            this.notification.add(
                `Carpeta creada. Se están procesando ${this.formatNumber(result.job.matched)} MLAs.`,
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo importar el archivo.",
                { type: "danger" }
            );
        } finally {
            this.state.importingFile = false;
        }
    }

    async refreshImportJob() {
        const job = this.state.importJob;
        if (!job?.id || !["queued", "running"].includes(job.state)) {
            return;
        }
        try {
            const updated = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_selection_job",
                [job.id]
            );
            const finished = ["done", "failed"].includes(updated.state);
            this.state.importJob = updated;
            if (finished) {
                await this.loadFolders();
                if (updated.state === "done") {
                    this.notification.add("La carpeta terminó de importar los MLAs.", {
                        type: "success",
                    });
                }
            } else if (String(updated.folderId) === String(this.state.selectedFolderId)) {
                await this.loadSelectedFolderProducts();
            }
        } catch {
            // El siguiente ciclo volverá a consultar el estado.
        }
    }

    get importProgress() {
        const total = Number(this.state.importJob?.matched || 0);
        const processed = Number(this.state.importJob?.processed || 0);
        return total ? Math.min(Math.round((processed / total) * 100), 100) : 0;
    }

    openDeleteFolder(folder) {
        this.state.deletingFolder = folder;
    }

    closeDeleteFolder() {
        this.state.deletingFolder = null;
    }

    async confirmDeleteFolder() {
        const folder = this.state.deletingFolder;
        if (!folder) {
            return;
        }
        try {
            await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "delete_selection_folder",
                [folder.id]
            );
            this.state.deletingFolder = null;
            this.notification.add("Carpeta eliminada.", { type: "success" });
            await this.loadFolders();
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo eliminar la carpeta.",
                { type: "danger" }
            );
        }
    }

    async downloadFolderCsv(folder) {
        if (!this.selectedColumnCount) {
            this.notification.add("Selecciona al menos una columna para el CSV.", {
                type: "warning",
            });
            return;
        }
        this.state.exportingFolderId = String(folder.id);
        try {
            const params = new URLSearchParams({
                columns: this.selectedColumnKeys.join(","),
            });
            const anchor = document.createElement("a");
            anchor.href = `/lqa_admin_panel/mercadolibre/selections/${encodeURIComponent(folder.id)}/csv?${params.toString()}`;
            anchor.download = "";
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            this.notification.add(
                `La descarga de ${this.formatNumber(folder.productCount)} publicaciones comenzo. El archivo se genera por lotes.`,
                { type: "info" }
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo descargar el CSV.",
                { type: "danger" }
            );
        } finally {
            this.state.exportingFolderId = "";
        }
    }

    isSelectedFolder(folder) {
        return String(folder.id) === String(this.state.selectedFolderId);
    }

    isExportingFolder(folder) {
        return String(folder.id) === String(this.state.exportingFolderId);
    }

    isColumnSelected(column) {
        return Boolean(this.state.selectedColumns[column.key]);
    }

    formatNumber(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0";
        }
        return new Intl.NumberFormat("es-AR").format(numericValue);
    }

    formatCurrency(value, currency = "ARS", digits = 0) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "-";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: currency || "ARS",
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(numericValue);
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
                not_found: "No encontrada",
            }[status] || status || "Sin estado"
        );
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.mercadolibre_selections", LqaMercadolibreSelections);
