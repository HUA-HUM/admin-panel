/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LqaAutomeliSelections extends Component {
    static template = "lqa_admin_panel.AutomeliSelections";

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

    async loadFolders() {
        this.state.loadingFolders = true;
        try {
            this.state.folders = await this.orm.call(
                "lqa.automeli.catalog.service",
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
                "lqa.automeli.catalog.service",
                "get_selection_products",
                [Number(this.state.selectedFolderId), 500, 0]
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
                "lqa.automeli.catalog.service",
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
        this.state.exportingFolderId = String(folder.id);
        try {
            const result = await this.orm.call(
                "lqa.automeli.catalog.service",
                "export_selection_folder_mlas",
                [folder.id]
            );
            this.downloadTextFile(result.filename, result.content);
            this.notification.add(
                `CSV generado con ${this.formatNumber(result.count)} MLAs.`,
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
        anchor.download = filename || "automeli-mlas.csv";
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
            currency,
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
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

    productUrl(product) {
        return product.mla
            ? `https://articulo.mercadolibre.com.ar/${product.mla}`
            : false;
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.automeli_selections", LqaAutomeliSelections);
