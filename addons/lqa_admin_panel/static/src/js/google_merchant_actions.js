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
            confirmation: "",
            publishForm: {
                limit: "5",
                offset: "0",
                maxPages: "1",
            },
            publishing: false,
            executing: false,
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

    get canPublish() {
        return (
            Number(this.state.publishForm.limit) > 0 &&
            Number(this.state.publishForm.offset) >= 0 &&
            Number(this.state.publishForm.maxPages) > 0 &&
            !this.state.publishing
        );
    }

    async executePublishAll() {
        if (!this.canPublish) {
            this.notification.add("Revisa limit, offset y maxPages.", {
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
                        maxPages: this.state.publishForm.maxPages,
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
                delete_selected: "Eliminación de productos seleccionados",
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
                request.maxPages ? `maxPages ${request.maxPages}` : "",
            ].filter(Boolean);
            return (
                run.message ||
                run.error_message ||
                (parts.length ? `Solicitud enviada: ${parts.join(", ")}.` : "")
            );
        }
        if (run.action_type === "delete_selected") {
            const deletedCount = Number(response.deleted_count || 0);
            const failedCount = Number(response.failed_count || 0);
            if (deletedCount || failedCount) {
                return `${deletedCount} eliminados, ${failedCount} con error.`;
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
