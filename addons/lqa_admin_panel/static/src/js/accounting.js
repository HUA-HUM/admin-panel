/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const emptyXubio = () => ({
    items: [],
    pagination: {
        total: 0,
        count: 0,
        limit: 50,
        offset: 0,
        page: 1,
        has_previous: false,
        has_next: false,
        next_offset: 50,
    },
});

export class LqaAccounting extends Component {
    static template = "lqa_admin_panel.Accounting";

    setup() {
        const params = this.props.action?.params || {};
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            view: params.view || "dashboard",
            activeTab: "clients",
            clients: {
                fileName: "",
                fileContent: "",
                manualInput: "",
                running: false,
                loadingJobs: false,
                jobs: [],
                selectedJob: null,
            },
            xubio: {
                loading: false,
                filters: {
                    tlqvCode: "",
                    numeroDocumento: "",
                    clienteCodigo: "",
                    mlOrderId: "",
                    documentKind: "",
                    fechaDesde: "",
                    fechaHasta: "",
                    limit: 50,
                    offset: 0,
                },
                result: emptyXubio(),
            },
        });

        onWillStart(async () => {
            if (this.isArcaBilling) {
                await this.loadArcaData();
            }
        });
    }

    get isDashboard() {
        return this.state.view === "dashboard";
    }

    get isArcaBilling() {
        return this.state.view === "arca_billing";
    }

    get pageTitle() {
        return this.isArcaBilling ? "Facturacion ARCA" : "Administracion";
    }

    get pageSubtitle() {
        return this.isArcaBilling
            ? "Clientes fiscales y comprobantes de ventas."
            : "Area administrativa, contable y fiscal.";
    }

    get selectedJobLines() {
        return this.state.clients.selectedJob?.lines || [];
    }

    get selectedJobSummary() {
        const job = this.state.clients.selectedJob;
        if (!job) {
            return "Sin lote seleccionado";
        }
        return `${this.formatNumber(job.inputCount)} TLQV procesados`;
    }

    async openDashboard() {
        this.state.view = "dashboard";
    }

    async openArcaBilling() {
        this.state.view = "arca_billing";
        await this.loadArcaData();
    }

    async loadArcaData() {
        await Promise.all([this.loadClientJobs(), this.searchComprobantes()]);
    }

    setTab(tab) {
        this.state.activeTab = tab;
    }

    async onClientFileChange(event) {
        const file = event.target.files?.[0];
        if (!file) {
            this.state.clients.fileName = "";
            this.state.clients.fileContent = "";
            return;
        }
        this.state.clients.fileName = file.name;
        this.state.clients.fileContent = await this.readTextFile(file);
    }

    readTextFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(reader.error);
            reader.readAsText(file);
        });
    }

    async runClientCreation() {
        if (!this.state.clients.fileContent && !this.state.clients.manualInput) {
            this.notification.add("Carga un CSV o pega codigos TLQV.", {
                type: "warning",
            });
            return;
        }
        this.state.clients.running = true;
        try {
            const job = await this.orm.call(
                "lqa.accounting.service",
                "create_clients_from_tlqv_csv",
                [
                    this.state.clients.fileContent,
                    this.state.clients.fileName,
                    this.state.clients.manualInput,
                ]
            );
            this.state.clients.selectedJob = job;
            await this.loadClientJobs(job.id);
            this.notification.add("Lote TLQV procesado.", { type: "success" });
        } catch (error) {
            this.notifyError(error, "No se pudo procesar el lote TLQV.");
        } finally {
            this.state.clients.running = false;
        }
    }

    async loadClientJobs(preferJobId = false) {
        this.state.clients.loadingJobs = true;
        try {
            const jobs = await this.orm.call(
                "lqa.accounting.service",
                "get_tlqv_client_jobs",
                [30]
            );
            this.state.clients.jobs = jobs;
            const selected =
                (preferJobId && jobs.find((job) => job.id === preferJobId)) ||
                jobs.find((job) => job.id === this.state.clients.selectedJob?.id) ||
                jobs[0] ||
                null;
            this.state.clients.selectedJob = selected;
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el historial TLQV.");
        } finally {
            this.state.clients.loadingJobs = false;
        }
    }

    selectJob(job) {
        this.state.clients.selectedJob = job;
    }

    async searchComprobantes(offset = 0) {
        this.state.xubio.loading = true;
        this.state.xubio.filters.offset = offset;
        try {
            this.state.xubio.result = await this.orm.call(
                "lqa.accounting.service",
                "get_xubio_comprobantes",
                [this.state.xubio.filters]
            );
        } catch (error) {
            this.state.xubio.result = emptyXubio();
            this.notifyError(error, "No se pudieron cargar comprobantes Xubio.");
        } finally {
            this.state.xubio.loading = false;
        }
    }

    clearComprobantesFilters() {
        Object.assign(this.state.xubio.filters, {
            tlqvCode: "",
            numeroDocumento: "",
            clienteCodigo: "",
            mlOrderId: "",
            documentKind: "",
            fechaDesde: "",
            fechaHasta: "",
            offset: 0,
        });
        this.searchComprobantes();
    }

    previousComprobantesPage() {
        const pagination = this.state.xubio.result.pagination;
        if (!pagination.has_previous) {
            return;
        }
        const offset = Math.max(Number(pagination.offset || 0) - Number(pagination.limit || 50), 0);
        this.searchComprobantes(offset);
    }

    nextComprobantesPage() {
        const pagination = this.state.xubio.result.pagination;
        if (!pagination.has_next) {
            return;
        }
        this.searchComprobantes(Number(pagination.next_offset || 0));
    }

    stateLabel(value) {
        return (
            {
                done: "Listo",
                partial: "Parcial",
                failed: "Fallido",
                processing: "Procesando",
                success: "Creado",
                issue: "Con issue",
            }[value] || this.humanize(value)
        );
    }

    stateClass(value) {
        if (["done", "success"].includes(value)) {
            return "is-green";
        }
        if (["partial", "issue"].includes(value)) {
            return "is-amber";
        }
        if (["failed"].includes(value)) {
            return "is-red";
        }
        return "is-blue";
    }

    formatNumber(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0";
        }
        return new Intl.NumberFormat("es-AR").format(numericValue);
    }

    formatCurrency(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "-";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: "ARS",
            maximumFractionDigits: 0,
        }).format(numericValue);
    }

    formatDate(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
            dateStyle: "short",
            timeStyle: "short",
        }).format(date);
    }

    humanize(value) {
        const cleanValue = String(value || "").trim();
        if (!cleanValue) {
            return "Sin dato";
        }
        return cleanValue
            .toLowerCase()
            .replace(/[_-]+/g, " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase());
    }

    notifyError(error, fallback) {
        const message =
            error?.data?.message ||
            error?.message ||
            error?.toString?.() ||
            fallback;
        this.notification.add(message, { type: "danger" });
    }
}

registry.category("actions").add("lqa_admin_panel.accounting", LqaAccounting);
