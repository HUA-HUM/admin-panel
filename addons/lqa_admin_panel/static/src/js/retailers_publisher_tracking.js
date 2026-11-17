/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// La guia de products-api pide 3-5 s mientras la pantalla esta abierta.
const POLL_MS = 4000;
const LAST_RUN_KEY = "lqaPublisherRunId";
// Fravega procesa como maximo 30 SKUs por minuto.
const FRAVEGA_SKUS_PER_MINUTE = 30;

// Motivos de error_message segun la guia de products-api. Los no listados se
// muestran tal cual: la lista puede crecer del lado del worker.
const REASONS = {
    PRODUCT_ALREADY_EXISTS: "Ya está publicado en Fravega",
    ALREADY_EXISTS_IN_FRAVEGA: "Fravega dice que ya existe",
    OUT_OF_STOCK: "Sin stock en Mercado Libre",
    MISSING_BRAND: "Falta la marca en Mercado Libre",
    MISSING_TITLE: "Falta el título en Mercado Libre",
    MISSING_IMAGES: "Faltan imágenes en Mercado Libre",
    CATEGORY_NOT_FOUND: "No hay categoría equivalente en Fravega",
    PRODUCT_NOT_FOUND: "El SKU no está en el catálogo de Mercado Libre",
    NO_CLASSIC_LISTING: "No tiene publicación clásica en Mercado Libre",
    INVALID_PRICE: "Precio inválido",
    PRICE_MAPPING_FAILED: "No se pudo calcular el precio",
    MISSING_REQUIRED_ATTRIBUTES: "Faltan atributos obligatorios de la categoría",
    IMAGE_PROCESSING_FAILED: "Ninguna imagen se pudo procesar",
    FRAVEGA_API_ERROR: "Error devuelto por Fravega",
};

const MELI_STATUS = {
    PAUSED: "pausada",
    CLOSED: "cerrada",
    UNDER_REVIEW: "en revisión",
    INACTIVE: "inactiva",
};

const STATUS = {
    pending: { label: "En cola", tone: "is-pending" },
    processing: { label: "Publicando", tone: "is-processing" },
    success: { label: "Publicado", tone: "is-success" },
    skipped: { label: "Omitido", tone: "is-skipped" },
    failed: { label: "Fallido", tone: "is-error" },
};

export class LqaRetailersPublisherTracking extends Component {
    static template = "lqa_admin_panel.RetailersPublisherTracking";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.action = useService("action");

        let storedRunId = "";
        try {
            storedRunId = window.sessionStorage.getItem(LAST_RUN_KEY) || "";
        } catch {
            storedRunId = "";
        }
        const contextRunId = String(this.props.action?.context?.lqa_publisher_run_id || "");

        this.state = useState({
            mode: "run",
            runId: contextRunId || storedRunId,
            manualRunId: "",
            history: [],
            folders: [],
            run: null,
            jobs: [],
            jobsPagination: {},
            jobsStatus: "",
            jobsLimit: 50,
            jobsOffset: 0,
            pendingJobs: [],
            pendingTotal: 0,
            loadingRun: false,
            loadingJobs: false,
            loadingPending: false,
            lastUpdatedAt: 0,
            now: Date.now(),
        });

        this.pollTimer = null;
        this.polling = false;

        onWillStart(async () => {
            await this.loadContext();
            if (!this.state.runId && this.state.history.length) {
                this.state.runId = String(this.state.history[0].run_id || "");
            }
            if (this.state.runId) {
                await this.refreshRun({ withJobs: true });
            }
        });

        onMounted(() => {
            this.pollTimer = setInterval(() => this.tick(), POLL_MS);
        });

        onWillUnmount(() => {
            clearInterval(this.pollTimer);
        });
    }

    // ------------------------------------------------------------ getters

    get runOptions() {
        return this.state.history.filter(
            (execution) => execution.run_id && !this.isHistoryError(execution)
        );
    }

    get currentExecution() {
        return this.state.history.find(
            (execution) => String(execution.run_id) === String(this.state.runId)
        );
    }

    get runFolderName() {
        const execution = this.currentExecution;
        if (!execution) {
            return "";
        }
        const folder = this.state.folders.find(
            (item) => String(item.id) === String(execution.folder_id)
        );
        return folder ? folder.name : `Carpeta #${execution.folder_id}`;
    }

    get isLive() {
        return Boolean(this.state.run && !this.state.run.finished);
    }

    get inFlight() {
        const run = this.state.run;
        return run ? run.pending + run.processing : 0;
    }

    // Segmentos de la barra, en % del total.
    get segments() {
        const run = this.state.run;
        if (!run || !run.totalJobs) {
            return { success: 0, skipped: 0, failed: 0 };
        }
        const pct = (value) => (value * 100) / run.totalJobs;
        return {
            success: pct(run.success),
            skipped: pct(run.skipped),
            failed: pct(run.failed),
        };
    }

    get remainingLabel() {
        if (!this.isLive || !this.inFlight) {
            return "";
        }
        const minutes = Math.ceil(this.inFlight / FRAVEGA_SKUS_PER_MINUTE);
        if (minutes <= 1) {
            return "menos de un minuto";
        }
        if (minutes < 60) {
            return `al menos ${minutes} min`;
        }
        const hours = Math.floor(minutes / 60);
        const rest = minutes % 60;
        return rest ? `al menos ${hours} h ${rest} min` : `al menos ${hours} h`;
    }

    get updatedLabel() {
        if (!this.state.lastUpdatedAt) {
            return "";
        }
        const seconds = Math.max(0, Math.round((this.state.now - this.state.lastUpdatedAt) / 1000));
        return seconds < 5 ? "recién" : `hace ${seconds} s`;
    }

    get statusFilters() {
        const run = this.state.run || {};
        return [
            { id: "", label: "Todos", count: run.totalJobs },
            { id: "failed", label: "Fallidos", count: run.failed },
            { id: "skipped", label: "Omitidos", count: run.skipped },
            { id: "success", label: "Publicados", count: run.success },
            { id: "processing", label: "Publicando", count: run.processing },
            { id: "pending", label: "En cola", count: run.pending },
        ];
    }

    get jobsRangeLabel() {
        const total = this.state.jobsPagination.total || 0;
        if (!total) {
            return "";
        }
        const from = this.state.jobsOffset + 1;
        const to = Math.min(this.state.jobsOffset + this.state.jobs.length, total);
        return `${this.formatNumber(from)}–${this.formatNumber(to)} de ${this.formatNumber(total)}`;
    }

    // ------------------------------------------------------------ carga

    async loadContext() {
        try {
            const [history, folders] = await Promise.all([
                this.orm.call("lqa.retailers.publisher.service", "get_publication_history", [30]),
                // Solo para poner nombre a las carpetas: sin conteos, que cuestan
                // una consulta por carpeta.
                this.orm.call("lqa.retailers.publisher.service", "get_folders", [false]),
            ]);
            this.state.history = history || [];
            this.state.folders = folders || [];
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el historial de publicaciones.");
        }
    }

    async refreshRun({ withJobs = false, quiet = false } = {}) {
        const runId = String(this.state.runId || "").trim();
        if (!runId) {
            return;
        }
        if (!quiet) {
            this.state.loadingRun = true;
        }
        try {
            const [run] = await Promise.all([
                this.orm.call("lqa.retailers.publisher.service", "get_publication_run", [runId]),
                withJobs ? this.loadJobs({ quiet }) : Promise.resolve(),
            ]);
            this.state.run = run;
            this.state.lastUpdatedAt = Date.now();
            this.state.now = Date.now();
            try {
                window.sessionStorage.setItem(LAST_RUN_KEY, runId);
            } catch {
                // sessionStorage puede no estar disponible: solo es comodidad.
            }
        } catch (error) {
            if (!quiet) {
                this.state.run = null;
                this.notifyError(error, `No se pudo consultar la publicación #${runId}.`);
            }
        } finally {
            this.state.loadingRun = false;
        }
    }

    async loadJobs({ quiet = false } = {}) {
        const runId = String(this.state.runId || "").trim();
        if (!runId) {
            return;
        }
        if (!quiet) {
            this.state.loadingJobs = true;
        }
        try {
            const response = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_publication_run_jobs",
                [runId, this.state.jobsLimit, this.state.jobsOffset, this.state.jobsStatus || null]
            );
            this.state.jobs = response.jobs || [];
            this.state.jobsPagination = response.pagination || {};
        } catch (error) {
            if (!quiet) {
                this.state.jobs = [];
                this.state.jobsPagination = {};
                this.notifyError(error, "No se pudo consultar el detalle por SKU.");
            }
        } finally {
            this.state.loadingJobs = false;
        }
    }

    async loadPendingJobs() {
        this.state.loadingPending = true;
        try {
            const response = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_pending_publications",
                [100]
            );
            this.state.pendingJobs = response.jobs || [];
            this.state.pendingTotal = response.total || 0;
        } catch (error) {
            this.state.pendingJobs = [];
            this.notifyError(error, "No se pudo consultar la cola.");
        } finally {
            this.state.loadingPending = false;
        }
    }

    // Cada POLL_MS: refresca contadores y la pagina visible mientras el run
    // tenga algo en vuelo. Con la pestana oculta no consulta; al terminar,
    // deja de pedir y solo avanza el reloj de "actualizado hace".
    async tick() {
        this.state.now = Date.now();
        if (document.hidden || this.polling || this.state.mode !== "run" || !this.isLive) {
            return;
        }
        this.polling = true;
        try {
            await this.refreshRun({ withJobs: true, quiet: true });
        } finally {
            this.polling = false;
        }
    }

    // ------------------------------------------------------------ acciones

    async setMode(mode) {
        this.state.mode = mode;
        if (mode === "pending") {
            await this.loadPendingJobs();
        }
    }

    async selectRun(runId) {
        runId = String(runId || "").trim().replace(/^#/, "");
        if (!runId || runId === String(this.state.runId)) {
            return;
        }
        this.state.runId = runId;
        this.state.run = null;
        this.state.jobs = [];
        this.state.jobsStatus = "";
        this.state.jobsOffset = 0;
        await this.refreshRun({ withJobs: true });
    }

    isCurrentRun(execution) {
        return String(execution.run_id) === String(this.state.runId);
    }

    async selectRunFromQueue(runId) {
        this.state.mode = "run";
        await this.selectRun(runId);
    }

    async onRunSelectChange(event) {
        await this.selectRun(event.target.value);
    }

    async searchManualRun() {
        const value = this.state.manualRunId;
        this.state.manualRunId = "";
        await this.selectRun(value);
    }

    async setJobsStatus(status) {
        if (status === this.state.jobsStatus) {
            return;
        }
        this.state.jobsStatus = status;
        this.state.jobsOffset = 0;
        await this.loadJobs();
    }

    async previousJobsPage() {
        this.state.jobsOffset = Math.max(this.state.jobsOffset - this.state.jobsLimit, 0);
        await this.loadJobs();
    }

    async nextJobsPage() {
        this.state.jobsOffset += this.state.jobsLimit;
        await this.loadJobs();
    }

    async manualRefresh() {
        await this.refreshRun({ withJobs: true });
    }

    openPublish() {
        this.action.doAction("lqa_admin_panel.action_lqa_retailers_publisher_execute");
    }

    // ------------------------------------------------------------ formato

    statusLabel(value) {
        return STATUS[String(value || "").toLowerCase()]?.label || value || "Sin estado";
    }

    statusTone(value) {
        return STATUS[String(value || "").toLowerCase()]?.tone || "is-pending";
    }

    reasonLabel(job) {
        const code = String(job.error_message || "").trim();
        if (!code) {
            return "";
        }
        const upper = code.toUpperCase();
        if (REASONS[upper]) {
            return REASONS[upper];
        }
        const meli = upper.match(/^MELI_STATUS_(.+)$/);
        if (meli) {
            const label = MELI_STATUS[meli[1]] || meli[1].toLowerCase().replace(/_/g, " ");
            return `La publicación de Mercado Libre está ${label}`;
        }
        return code;
    }

    // El codigo crudo se muestra debajo solo cuando la traduccion lo oculta.
    reasonCode(job) {
        const code = String(job.error_message || "").trim();
        return code && this.reasonLabel(job) !== code ? code : "";
    }

    stageLabel(stage) {
        return String(stage || "").replace(/_/g, " ");
    }

    runOptionLabel(execution) {
        const folder = this.state.folders.find(
            (item) => String(item.id) === String(execution.folder_id)
        );
        const name = folder ? folder.name : `Carpeta #${execution.folder_id}`;
        return `#${execution.run_id} · ${name} · ${this.formatDateTime(execution.triggered_at)}`;
    }

    isHistoryError(execution) {
        return ["ERROR", "FAILED"].includes(String(execution.status || "").toUpperCase());
    }

    marketplaceLabel(value) {
        return (
            { fravega: "Fravega", megatone: "Megatone", oncity: "OnCity" }[
                String(value || "").toLowerCase()
            ] || value || "—"
        );
    }

    formatPercent(value) {
        return `${Math.round(Number(value) || 0)}%`;
    }

    formatNumber(value) {
        const numericValue = Number(value);
        return new Intl.NumberFormat("es-AR").format(
            Number.isFinite(numericValue) ? numericValue : 0
        );
    }

    formatDateTime(value) {
        if (!value) {
            return "—";
        }
        // Odoo guarda UTC sin zona: sin la Z quedaria corrido tres horas.
        const iso = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
            ? `${value.replace(" ", "T")}Z`
            : value;
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    formatTime(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
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
    .add("lqa_admin_panel.retailers_publisher_tracking", LqaRetailersPublisherTracking);
