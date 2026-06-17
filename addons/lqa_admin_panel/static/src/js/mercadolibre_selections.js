/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const CSV_COLUMNS = [
    { key: "item_id", label: "MLA" },
    { key: "title", label: "Titulo" },
    { key: "sku", label: "SKU" },
    { key: "brand", label: "Marca" },
    { key: "status", label: "Estado" },
    { key: "condition", label: "Condicion" },
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
    "price",
    "available_quantity",
    "permalink",
];

const defaultSelectedColumns = () =>
    Object.fromEntries(DEFAULT_COLUMNS.map((key) => [key, true]));

export class LqaMercadolibreSelections extends Component {
    static template = "lqa_admin_panel.MercadolibreSelections";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
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
        });

        onWillStart(async () => {
            await this.loadFolders();
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
            const result = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "export_selection_folder_csv",
                [folder.id, this.selectedColumnKeys]
            );
            this.downloadTextFile(result.filename, result.content);
            this.notification.add(
                `CSV generado con ${this.formatNumber(result.count)} publicaciones.`,
                { type: "success" }
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

    downloadTextFile(filename, content) {
        const blob = new Blob([content || ""], {
            type: "text/csv;charset=utf-8",
        });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename || "mercadolibre-seleccion.csv";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
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
            }[status] || status || "Sin estado"
        );
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.mercadolibre_selections", LqaMercadolibreSelections);
