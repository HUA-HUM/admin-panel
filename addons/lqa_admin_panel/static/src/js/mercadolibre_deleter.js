/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const extractMlas = (value) => {
    const matches = String(value || "").toUpperCase().match(/MLA\d+/g) || [];
    return [...new Set(matches)];
};

export class LqaMercadolibreDeleter extends Component {
    static template = "lqa_admin_panel.MercadolibreDeleter";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            idsText: "",
            parsedIds: [],
            appKey: "default",
            history: [],
            loadingHistory: true,
            processing: false,
            showConfirmation: false,
            csvName: "",
        });

        onWillStart(async () => {
            await this.loadHistory();
        });
    }

    async loadHistory() {
        this.state.loadingHistory = true;
        try {
            this.state.history = await this.orm.call(
                "lqa.mercadolibre.deletion.service",
                "get_history",
                [50]
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo cargar el historial.",
                { type: "danger" }
            );
        } finally {
            this.state.loadingHistory = false;
        }
    }

    onIdsInput(event) {
        this.state.idsText = event.target.value;
        this.state.parsedIds = extractMlas(this.state.idsText);
    }

    async onCsvSelected(event) {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }
        const content = await file.text();
        const ids = extractMlas(content);
        this.state.csvName = file.name;
        this.state.parsedIds = ids;
        this.state.idsText = ids.join("\n");
        event.target.value = "";
        this.notification.add(
            `${ids.length} publicaciones validas encontradas en el archivo.`,
            { type: ids.length ? "success" : "warning" }
        );
    }

    clearIds() {
        this.state.idsText = "";
        this.state.parsedIds = [];
        this.state.csvName = "";
    }

    openConfirmation() {
        if (!this.state.parsedIds.length) {
            this.notification.add("Ingresa al menos un MLA valido.", {
                type: "warning",
            });
            return;
        }
        this.state.showConfirmation = true;
    }

    closeConfirmation() {
        if (!this.state.processing) {
            this.state.showConfirmation = false;
        }
    }

    async confirmDeletion() {
        this.state.processing = true;
        try {
            const result = await this.orm.call(
                "lqa.mercadolibre.deletion.service",
                "delete_products",
                [this.state.parsedIds, this.state.appKey]
            );
            this.notification.add(result.message, {
                type: result.ok ? "success" : "danger",
            });
            this.state.showConfirmation = false;
            if (result.ok) {
                this.clearIds();
            }
            await this.loadHistory();
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo ejecutar la eliminacion.",
                { type: "danger" }
            );
        } finally {
            this.state.processing = false;
        }
    }

    formatDateTime(value) {
        if (!value) {
            return "-";
        }
        return new Intl.DateTimeFormat("es-AR", {
            dateStyle: "short",
            timeStyle: "short",
        }).format(new Date(`${value}Z`));
    }

    statusLabel(status) {
        return (
            {
                completed: "Completado",
                partial: "Parcial",
                failed: "Fallido",
                processing: "Procesando",
                deleted: "Eliminado",
            }[status] || status
        );
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.mercadolibre_deleter", LqaMercadolibreDeleter);
