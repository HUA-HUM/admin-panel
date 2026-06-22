/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const CONFIRMATION_TEXT = "ELIMINAR TODO";

export class LqaGoogleMerchantActions extends Component {
    static template = "lqa_admin_panel.GoogleMerchantActions";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            activePanel: "publisher",
            confirmation: "",
            publishForm: {
                limit: "50",
                offset: "0",
            },
            manualDelete: {
                sku: "",
                contentLanguage: "es",
                feedLabel: "AR",
            },
            deleteFile: {
                filename: "",
                content: "",
            },
            publishing: false,
            executing: false,
            deletingOne: false,
            deletingFile: false,
            downloadingCatalog: false,
            loadingHistory: true,
            history: [],
            expandedResponses: {},
        });

        onWillStart(async () => {
            await this.loadHistory();
        });
    }

    get canExecute() {
        return (
            this.state.confirmation.trim().toUpperCase() === CONFIRMATION_TEXT &&
            !this.state.executing
        );
    }

    get canDownloadCatalog() {
        return !this.state.downloadingCatalog;
    }

    setPanel(panel) {
        this.state.activePanel = panel;
    }

    isPanel(panel) {
        return this.state.activePanel === panel;
    }

    get canPublish() {
        return (
            Number(this.state.publishForm.limit) > 0 &&
            Number(this.state.publishForm.offset) >= 0 &&
            !this.state.publishing
        );
    }

    get canDeleteOne() {
        return Boolean(
            this.state.manualDelete.sku.trim() &&
                this.state.manualDelete.contentLanguage.trim() &&
                this.state.manualDelete.feedLabel.trim() &&
                !this.state.deletingOne
        );
    }

    get canDeleteFile() {
        return Boolean(
            this.state.deleteFile.filename &&
                this.state.deleteFile.content &&
                !this.state.deletingFile
        );
    }

    async executePublishAll() {
        if (!this.canPublish) {
            this.notification.add("Revisa limit y offset.", {
                type: "warning",
            });
            return;
        }
        this.state.publishing = true;
        try {
            const result = await this.orm.call(
                "lqa.google.merchant.actions.service",
                "publish_all_products",
                [
                    {
                        limit: this.state.publishForm.limit,
                        offset: this.state.publishForm.offset,
                    },
                ]
            );
            this.notification.add(
                result.message ||
                    result.error_message ||
                    "La carga masiva fue enviada.",
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
            this.notifyError(error, "No se pudo iniciar la carga masiva.");
        } finally {
            await this.loadHistory();
            this.state.publishing = false;
        }
    }

    async executeDeleteOne() {
        if (!this.canDeleteOne) {
            this.notification.add("Completá SKU, idioma y etiqueta de feed.", {
                type: "warning",
            });
            return;
        }
        this.state.deletingOne = true;
        try {
            const result = await this.orm.call(
                "lqa.google.merchant.actions.service",
                "delete_selected_products",
                [
                    [
                        {
                            sku: this.state.manualDelete.sku,
                            contentLanguage: this.state.manualDelete.contentLanguage,
                            feedLabel: this.state.manualDelete.feedLabel,
                        },
                    ],
                ]
            );
            this.state.manualDelete.sku = "";
            this.notification.add(
                result.message ||
                    result.error_message ||
                    "La eliminación fue registrada.",
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
            await this.loadHistory();
            this.state.deletingOne = false;
        }
    }

    async executeDeleteFile() {
        if (!this.canDeleteFile) {
            this.notification.add("Seleccioná un archivo CSV o XLSX.", {
                type: "warning",
            });
            return;
        }
        this.state.deletingFile = true;
        try {
            const result = await this.orm.call(
                "lqa.google.merchant.actions.service",
                "delete_products_from_file",
                [this.state.deleteFile.filename, this.state.deleteFile.content]
            );
            this.state.deleteFile.filename = "";
            this.state.deleteFile.content = "";
            this.notification.add(
                result.message ||
                    `Quedaron en cola ${result.requested_count || 0} productos.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo importar el archivo.");
        } finally {
            await this.loadHistory();
            this.state.deletingFile = false;
        }
    }

    async downloadDeleteCatalog() {
        this.state.downloadingCatalog = true;
        try {
            const result = await this.orm.call(
                "lqa.google.merchant.actions.service",
                "download_delete_catalog_xlsx",
                []
            );
            this.downloadBase64File(result.filename, result.content, result.mimetype);
            this.notification.add(
                `Catálogo descargado: ${result.total || 0} productos.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo descargar el catálogo.");
        } finally {
            this.state.downloadingCatalog = false;
        }
    }

    async executeDeleteAll() {
        if (!this.canExecute) {
            this.notification.add(
                `Escribí ${CONFIRMATION_TEXT} para confirmar.`,
                { type: "warning" }
            );
            return;
        }
        this.state.executing = true;
        try {
            const result = await this.orm.call(
                "lqa.google.merchant.actions.service",
                "delete_all_products",
                [this.state.confirmation]
            );
            this.state.confirmation = "";
            this.notification.add(
                result.status === "completed"
                    ? result.message || "La eliminación fue enviada correctamente."
                    : result.error_message || "La eliminación no pudo completarse.",
                { type: result.status === "completed" ? "success" : "danger" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo eliminar el catálogo.");
        } finally {
            await this.loadHistory();
            this.state.executing = false;
        }
    }

    onDeleteFileChange(event) {
        const file = event.target.files && event.target.files[0];
        if (!file) {
            this.state.deleteFile.filename = "";
            this.state.deleteFile.content = "";
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || "");
            this.state.deleteFile.filename = file.name;
            this.state.deleteFile.content = result.includes(",")
                ? result.split(",").pop()
                : result;
        };
        reader.onerror = () => {
            this.state.deleteFile.filename = "";
            this.state.deleteFile.content = "";
            this.notification.add("No se pudo leer el archivo.", { type: "danger" });
        };
        reader.readAsDataURL(file);
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
        anchor.download = filename || "google-merchant-catalogo-eliminador.xlsx";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    }

    onConfirmationKeydown(event) {
        if (event.key === "Enter") {
            this.executeDeleteAll();
        }
    }

    async loadHistory() {
        this.state.loadingHistory = true;
        try {
            this.state.history = await this.orm.call(
                "lqa.google.merchant.actions.service",
                "get_history",
                [30]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el historial.");
        } finally {
            this.state.loadingHistory = false;
        }
    }

    toggleResponse(run) {
        this.state.expandedResponses[run.id] =
            !this.state.expandedResponses[run.id];
    }

    statusLabel(value) {
        return (
            {
                processing: "Procesando",
                completed: "Completado",
                partial: "Parcial",
                failed: "Fallido",
            }[String(value || "").toLowerCase()] || value || "-"
        );
    }

    actionLabel(value) {
        return (
            {
                publish_all: "Carga masiva de productos",
                delete_all: "Eliminación total del catálogo",
                delete_selected: "Eliminación de productos Google Merchant",
            }[String(value || "").toLowerCase()] || "Acción Google Merchant"
        );
    }

    actionDetail(run) {
        const response = run.response || {};
        if (run.action_type === "publish_all") {
            const request = response.request || {};
            const parts = [
                request.limit ? `limit ${request.limit}` : "",
                request.offset !== undefined ? `offset ${request.offset}` : "",
            ].filter(Boolean);
            return (
                run.message ||
                run.error_message ||
                (parts.length ? `Solicitud enviada: ${parts.join(", ")}.` : "")
            );
        }
        if (run.action_type === "delete_selected") {
            const requestedCount = Number(
                run.requested_count || response.requested_count || 0
            );
            const deletedCount = Number(
                run.deleted_count || response.deleted_count || 0
            );
            const failedCount = Number(
                run.failed_count || response.failed_count || 0
            );
            const pendingCount = Number(
                run.pending_count || response.pending_count || 0
            );
            if (requestedCount || deletedCount || failedCount || pendingCount) {
                return `${deletedCount} eliminados, ${failedCount} con error, ${pendingCount} en cola de ${requestedCount}.`;
            }
        }
        return run.message || run.error_message || "Sin detalle adicional.";
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
            second: "2-digit",
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
    .add(
        "lqa_admin_panel.google_merchant_actions",
        LqaGoogleMerchantActions
    );
