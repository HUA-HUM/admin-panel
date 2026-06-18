/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LqaRetailersPublisher extends Component {
    static template = "lqa_admin_panel.RetailersPublisher";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.fileInput = null;
        this.state = useState({
            folders: [],
            selectedFolderId: "",
            loadingFolders: true,
            creatingFolder: false,
            addingManual: false,
            importingFile: false,
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
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar las carpetas de Madre.");
        } finally {
            this.state.loadingFolders = false;
        }
    }

    selectFolder(folder) {
        this.state.selectedFolderId = String(folder.id);
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
                    this.state.selectedFolderId = String(matchingFolder.id);
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
                [
                    this.selectedFolder.id,
                    [{ productId, sellerSku }],
                ]
            );
            this.state.manual.productId = "";
            this.state.manual.sellerSku = "";
            await this.loadFolders(this.selectedFolder.id);
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
            this.notification.add("Selecciona un archivo CSV o XLSX.", {
                type: "warning",
            });
            return;
        }
        this.state.importingFile = true;
        try {
            const folderId = this.selectedFolder.id;
            const result = await this.orm.call(
                "lqa.retailers.publisher.service",
                "import_products",
                [folderId, this.state.upload.name, this.state.upload.content]
            );
            this.clearUpload();
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

    clearUpload() {
        this.state.upload.name = "";
        this.state.upload.content = "";
        if (this.fileInput) {
            this.fileInput.value = "";
        }
    }

    downloadTemplate() {
        const content = "productId,sellerSku\nMLA123456789,SKU-001\n";
        const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "retailers-publicador-productos.csv";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    }

    readFileAsDataUrl(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }

    isSelectedFolder(folder) {
        return String(folder.id) === String(this.state.selectedFolderId);
    }

    formatNumber(value) {
        const numericValue = Number(value);
        return new Intl.NumberFormat("es-AR").format(
            Number.isFinite(numericValue) ? numericValue : 0
        );
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
    .add("lqa_admin_panel.retailers_publisher", LqaRetailersPublisher);
