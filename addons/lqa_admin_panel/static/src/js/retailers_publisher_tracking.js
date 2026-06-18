/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LqaRetailersPublisherTracking extends Component {
    static template = "lqa_admin_panel.RetailersPublisherTracking";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        const lastRunId = window.sessionStorage.getItem("lqaPublisherRunId") || "";
        this.state = useState({
            mode: lastRunId ? "run" : "pending",
            runId: lastRunId,
            runJobs: [],
            pendingJobs: [],
            runPagination: {},
            runLimit: "50",
            pendingLimit: "50",
            loadingRun: false,
            loadingPending: false,
            runLoaded: false,
        });

        onWillStart(async () => {
            if (this.state.runId) {
                await this.loadRunJobs(true);
            } else {
                await this.loadPendingJobs();
            }
        });
    }

    async setMode(mode) {
        this.state.mode = mode;
        if (mode === "pending" && !this.state.pendingJobs.length) {
            await this.loadPendingJobs();
        }
    }

    async searchRunJobs() {
        await this.loadRunJobs(true);
    }

    async loadRunJobs(resetOffset = false) {
        const runId = this.state.runId.trim();
        if (!runId) {
            this.notification.add("Ingresa un run ID.", { type: "warning" });
            return;
        }
        const offset = resetOffset
            ? 0
            : Number(this.state.runPagination.offset || 0);
        this.state.loadingRun = true;
        try {
            const response = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_publication_run_jobs",
                [runId, Number(this.state.runLimit), offset]
            );
            this.state.runJobs = response.jobs || [];
            this.state.runPagination = response.pagination || {};
            this.state.runLoaded = true;
            window.sessionStorage.setItem("lqaPublisherRunId", runId);
        } catch (error) {
            this.state.runJobs = [];
            this.state.runPagination = {};
            this.notifyError(error, "No se pudo consultar el publication run.");
        } finally {
            this.state.loadingRun = false;
        }
    }

    async previousRunPage() {
        const limit = Number(this.state.runPagination.limit || this.state.runLimit);
        this.state.runPagination.offset = Math.max(
            Number(this.state.runPagination.offset || 0) - limit,
            0
        );
        await this.loadRunJobs();
    }

    async nextRunPage() {
        this.state.runPagination.offset = Number(
            this.state.runPagination.next_offset || 0
        );
        await this.loadRunJobs();
    }

    async changeRunLimit() {
        await this.loadRunJobs(true);
    }

    async loadPendingJobs() {
        this.state.loadingPending = true;
        try {
            const response = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_pending_publications",
                [Number(this.state.pendingLimit)]
            );
            this.state.pendingJobs = response.jobs || [];
        } catch (error) {
            this.state.pendingJobs = [];
            this.notifyError(error, "No se pudieron consultar las publicaciones pendientes.");
        } finally {
            this.state.loadingPending = false;
        }
    }

    marketplaceLabel(value) {
        return (
            {
                fravega: "Fravega",
                megatone: "Megatone",
                oncity: "OnCity",
            }[String(value || "").toLowerCase()] || value || "-"
        );
    }

    statusLabel(value) {
        return (
            {
                PENDING: "Pendiente",
                QUEUED: "En cola",
                STARTED: "Iniciado",
                PROCESSING: "Procesando",
                RETRYING: "Reintentando",
                SUCCESS: "Correcto",
                COMPLETED: "Completado",
                FAILED: "Fallido",
                ERROR: "Error",
            }[String(value || "").toUpperCase()] || value || "Sin estado"
        );
    }

    statusClass(value) {
        const normalized = String(value || "").toUpperCase();
        if (["SUCCESS", "COMPLETED"].includes(normalized)) {
            return "is-success";
        }
        if (["FAILED", "ERROR"].includes(normalized)) {
            return "is-error";
        }
        if (["STARTED", "PROCESSING", "RETRYING"].includes(normalized)) {
            return "is-processing";
        }
        return "is-pending";
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
    .add(
        "lqa_admin_panel.retailers_publisher_tracking",
        LqaRetailersPublisherTracking
    );
