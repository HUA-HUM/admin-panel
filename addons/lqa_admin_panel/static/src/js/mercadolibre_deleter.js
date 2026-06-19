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
            reason: "",
            history: [],
            historySearch: "",
            lineSearches: {},
            reasonDrafts: {},
            editingReasonBatchId: null,
            savingReasonBatchId: null,
            loadingHistory: true,
            processing: false,
            showConfirmation: false,
            csvName: "",
        });

        onWillStart(async () => {
            await this.loadHistory();
        });
    }

    get normalizedHistorySearch() {
        return String(this.state.historySearch || "").trim().toUpperCase();
    }

    get filteredHistory() {
        const search = this.normalizedHistorySearch;
        if (!search) {
            return this.state.history;
        }
        return this.state.history.filter((batch) =>
            this.batchMatchesHistorySearch(batch, search)
        );
    }

    get historySearchResultsCount() {
        return this.filteredHistory.length;
    }

    get trimmedReason() {
        return String(this.state.reason || "").trim();
    }

    get canSubmitDeletion() {
        return Boolean(this.state.parsedIds.length && this.trimmedReason);
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
        this.state.reason = "";
    }

    openConfirmation() {
        if (!this.state.parsedIds.length) {
            this.notification.add("Ingresa al menos un MLA valido.", {
                type: "warning",
            });
            return;
        }
        if (!this.trimmedReason) {
            this.notification.add("Escribi un motivo para registrar el lote.", {
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
                [this.state.parsedIds, this.state.appKey, this.trimmedReason]
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

    onHistorySearchInput(event) {
        this.state.historySearch = event.target.value;
    }

    clearHistorySearch() {
        this.state.historySearch = "";
    }

    batchLineSearch(batch) {
        return this.state.lineSearches[batch.id] || "";
    }

    onBatchLineSearchInput(batch, event) {
        this.state.lineSearches[batch.id] = event.target.value;
    }

    clearBatchLineSearch(batch) {
        this.state.lineSearches[batch.id] = "";
    }

    batchMatchesHistorySearch(batch, search = this.normalizedHistorySearch) {
        if (!search) {
            return true;
        }
        const batchValues = [
            batch.id,
            batch.reason,
            batch.app_key,
            batch.user,
            batch.status,
        ]
            .map((value) => String(value || "").toUpperCase())
            .join(" ");
        if (batchValues.includes(search)) {
            return true;
        }
        return (batch.lines || []).some((line) =>
            this.lineMatchesSearch(line, search)
        );
    }

    batchLines(batch) {
        let lines = batch.lines || [];
        const historySearch = this.normalizedHistorySearch;
        if (historySearch) {
            const matchingLines = lines.filter((line) =>
                this.lineMatchesSearch(line, historySearch)
            );
            if (matchingLines.length) {
                lines = matchingLines;
            }
        }
        const lineSearch = String(this.batchLineSearch(batch) || "")
            .trim()
            .toUpperCase();
        if (lineSearch) {
            lines = lines.filter((line) => this.lineMatchesSearch(line, lineSearch));
        }
        return lines;
    }

    lineMatchesSearch(line, search) {
        return [line.mla, line.status, line.message]
            .map((value) => String(value || "").toUpperCase())
            .some((value) => value.includes(search));
    }

    batchLineCount(batch) {
        return (batch.lines || []).length;
    }

    batchLineResultsLabel(batch) {
        const total = this.batchLineCount(batch);
        const shown = this.batchLines(batch).length;
        return `${shown} de ${total} publicaciones`;
    }

    isEditingBatchReason(batch) {
        return this.state.editingReasonBatchId === batch.id;
    }

    isSavingBatchReason(batch) {
        return this.state.savingReasonBatchId === batch.id;
    }

    batchReasonDraft(batch) {
        const draft = this.state.reasonDrafts[batch.id];
        return draft === undefined || draft === null ? batch.reason || "" : draft;
    }

    startBatchReasonEdit(batch) {
        this.state.editingReasonBatchId = batch.id;
        this.state.reasonDrafts[batch.id] = batch.reason || "";
    }

    onBatchReasonInput(batch, event) {
        this.state.reasonDrafts[batch.id] = event.target.value;
    }

    cancelBatchReasonEdit(batch) {
        if (this.isSavingBatchReason(batch)) {
            return;
        }
        this.state.reasonDrafts[batch.id] = batch.reason || "";
        this.state.editingReasonBatchId = null;
    }

    async saveBatchReason(batch) {
        this.state.savingReasonBatchId = batch.id;
        try {
            const result = await this.orm.call(
                "lqa.mercadolibre.deletion.service",
                "update_batch_reason",
                [batch.id, this.batchReasonDraft(batch)]
            );
            this.state.history = this.state.history.map((item) =>
                item.id === batch.id ? { ...item, reason: result.reason } : item
            );
            this.state.reasonDrafts[batch.id] = result.reason;
            this.state.editingReasonBatchId = null;
            this.notification.add(result.message, { type: "success" });
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo guardar el motivo.",
                { type: "danger" }
            );
        } finally {
            this.state.savingReasonBatchId = null;
        }
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.mercadolibre_deleter", LqaMercadolibreDeleter);
