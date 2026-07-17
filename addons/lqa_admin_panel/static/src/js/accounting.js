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

const emptyClientIssues = () => ({
    items: [],
    pagination: {
        total: 0,
        count: 0,
        limit: 100,
        offset: 0,
        page: 1,
        has_previous: false,
        has_next: false,
        next_offset: 100,
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
            activeTab:
                params.view === "arca_billing"
                    ? "comprobantes"
                    : params.view === "xubio"
                    ? "xubio"
                    : "clients",
            clients: {
                activeTab: "fiscal",
                fileName: "",
                fileContent: "",
                manualInput: "",
                running: false,
                loadingJobs: false,
                jobs: [],
                selectedJob: null,
            },
            issueClients: {
                loading: false,
                creating: {},
                manualTlqv: "",
                manualRunning: false,
                filters: {
                    tlqvCode: "",
                    buyerName: "",
                    email: "",
                    documentoNroDigits: "",
                    limit: 100,
                    offset: 0,
                },
                result: emptyClientIssues(),
            },
            xubio: {
                loading: false,
                exporting: false,
                showExportFields: false,
                exportColumns: [],
                pdfLoadingTlqv: "",
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
            if (this.isWorkspace) {
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

    get isClients() {
        return this.state.view === "clients";
    }

    get isXubio() {
        return this.state.view === "xubio";
    }

    get isWorkspace() {
        return this.isArcaBilling || this.isClients || this.isXubio;
    }

    get pageTitle() {
        if (this.isClients) {
            return "Clientes";
        }
        if (this.isXubio) {
            return "Xubio";
        }
        return this.isArcaBilling ? "Comprobantes Xubio" : "Administracion";
    }

    get pageSubtitle() {
        if (this.isClients) {
            return "Clientes fiscales, issues de CUIT y altas como consumidor final.";
        }
        if (this.isXubio) {
            return "Clientes y comprobantes contables conectados a Xubio.";
        }
        return this.isArcaBilling
            ? "Consulta y auditoria de comprobantes sincronizados con Xubio."
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
        const operation =
            job.operationType === "consumer_final"
                ? "consumidor final"
                : "clientes TLQV";
        return `${this.formatNumber(job.inputCount)} ${operation} procesados`;
    }

    async openDashboard() {
        this.state.view = "dashboard";
    }

    async openBack() {
        if (this.isClients || this.isArcaBilling) {
            await this.openXubio();
            return;
        }
        await this.openDashboard();
    }

    async openArcaBilling() {
        this.state.view = "arca_billing";
        this.state.activeTab = "comprobantes";
        await this.loadArcaData();
    }

    async openClients() {
        this.state.view = "clients";
        this.state.activeTab = "clients";
        await this.loadArcaData();
    }

    async openXubio() {
        this.state.view = "xubio";
        this.state.activeTab = "xubio";
        await this.loadArcaData();
    }

    async loadArcaData() {
        if (this.isClients) {
            await Promise.all([this.loadClientJobs(), this.searchClientIssues()]);
            return;
        }
        if (this.isArcaBilling) {
            await Promise.all([this.loadXubioExportColumns(), this.searchComprobantes()]);
        }
    }

    setTab(tab) {
        this.state.activeTab = tab;
        this.state.view =
            tab === "comprobantes" ? "arca_billing" : tab === "xubio" ? "xubio" : "clients";
        this.loadArcaData();
    }

    setClientTab(tab) {
        this.state.clients.activeTab = tab;
        if (tab === "consumer") {
            this.searchClientIssues(this.state.issueClients.result.pagination.offset || 0);
        }
        if (tab === "records") {
            this.loadClientJobs(this.state.clients.selectedJob?.id || false);
        }
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

    async searchClientIssues(offset = 0) {
        this.state.issueClients.loading = true;
        this.state.issueClients.filters.offset = offset;
        try {
            this.state.issueClients.result = await this.orm.call(
                "lqa.accounting.service",
                "get_client_issue_clients",
                [this.state.issueClients.filters]
            );
        } catch (error) {
            this.state.issueClients.result = emptyClientIssues();
            this.notifyError(error, "No se pudieron cargar clientes con issue.");
        } finally {
            this.state.issueClients.loading = false;
        }
    }

    clearClientIssueFilters() {
        Object.assign(this.state.issueClients.filters, {
            tlqvCode: "",
            buyerName: "",
            email: "",
            documentoNroDigits: "",
            offset: 0,
        });
        this.searchClientIssues();
    }

    previousClientIssuesPage() {
        const pagination = this.state.issueClients.result.pagination;
        if (!pagination.has_previous) {
            return;
        }
        const offset = Math.max(
            Number(pagination.offset || 0) - Number(pagination.limit || 100),
            0
        );
        this.searchClientIssues(offset);
    }

    nextClientIssuesPage() {
        const pagination = this.state.issueClients.result.pagination;
        if (!pagination.has_next) {
            return;
        }
        this.searchClientIssues(Number(pagination.next_offset || 0));
    }

    async createConsumerFinal(issue) {
        const tlqvCode = issue?.tlqvCode;
        await this.createConsumerFinalFromTlqv(tlqvCode);
    }

    async createConsumerFinalManual() {
        const tlqvCode = this.state.issueClients.manualTlqv;
        if (!tlqvCode) {
            this.notification.add("Ingresa un TLQV para crear consumidor final.", {
                type: "warning",
            });
            return;
        }
        this.state.issueClients.manualRunning = true;
        try {
            const created = await this.createConsumerFinalFromTlqv(tlqvCode);
            if (created) {
                this.state.issueClients.manualTlqv = "";
            }
        } finally {
            this.state.issueClients.manualRunning = false;
        }
    }

    async createConsumerFinalFromTlqv(tlqvCode) {
        if (!tlqvCode) {
            this.notification.add("Indica un TLQV valido.", { type: "warning" });
            return false;
        }
        if (
            !window.confirm(
                `Crear consumidor final en Xubio para ${tlqvCode}?`
            )
        ) {
            return false;
        }
        this.state.issueClients.creating[tlqvCode] = true;
        try {
            const job = await this.orm.call(
                "lqa.accounting.service",
                "create_consumidor_final_from_issue",
                [tlqvCode]
            );
            this.state.clients.selectedJob = job;
            await Promise.all([
                this.loadClientJobs(job.id),
                this.searchClientIssues(this.state.issueClients.result.pagination.offset),
            ]);
            this.notification.add("Consumidor final creado/procesado.", {
                type: "success",
            });
            return true;
        } catch (error) {
            this.notifyError(error, "No se pudo crear el consumidor final.");
            return false;
        } finally {
            this.state.issueClients.creating[tlqvCode] = false;
        }
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

    async loadXubioExportColumns() {
        if (this.state.xubio.exportColumns.length) {
            return;
        }
        try {
            const columns = await this.orm.call(
                "lqa.accounting.service",
                "get_xubio_export_columns",
                []
            );
            this.state.xubio.exportColumns = columns.map((column) => ({
                ...column,
                selected: Boolean(column.default),
            }));
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar las columnas de exportacion.");
        }
    }

    get xubioSelectedColumnsCount() {
        return this.state.xubio.exportColumns.filter((column) => column.selected).length;
    }

    get xubioCurrentPageTotal() {
        return (this.state.xubio.result.items || []).reduce(
            (total, item) => total + (Number(item.importeTotal) || 0),
            0
        );
    }

    get xubioFiscalCount() {
        return (this.state.xubio.result.items || []).filter(
            (item) => item.fiscalmenteEmitido
        ).length;
    }

    get xubioExportColumnKeys() {
        const selected = this.state.xubio.exportColumns
            .filter((column) => column.selected)
            .map((column) => column.key);
        if (selected.length) {
            return selected;
        }
        return this.state.xubio.exportColumns
            .filter((column) => column.default)
            .map((column) => column.key);
    }

    toggleXubioExportFields() {
        this.state.xubio.showExportFields = !this.state.xubio.showExportFields;
    }

    toggleXubioExportColumn(column) {
        column.selected = !column.selected;
    }

    selectAllXubioExportColumns() {
        for (const column of this.state.xubio.exportColumns) {
            column.selected = true;
        }
    }

    resetXubioExportColumns() {
        for (const column of this.state.xubio.exportColumns) {
            column.selected = Boolean(column.default);
        }
    }

    async exportXubioComprobantes() {
        if (!this.xubioExportColumnKeys.length) {
            this.notification.add("Selecciona al menos una columna para exportar.", {
                type: "warning",
            });
            return;
        }
        this.state.xubio.exporting = true;
        try {
            const result = await this.orm.call(
                "lqa.accounting.service",
                "export_xubio_comprobantes_xlsx",
                [this.state.xubio.filters, this.xubioExportColumnKeys]
            );
            this.downloadBase64File(result.filename, result.content, result.mimetype);
            this.notification.add(
                `Excel generado con ${this.formatNumber(result.total)} comprobantes.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo exportar el Excel de comprobantes.");
        } finally {
            this.state.xubio.exporting = false;
        }
    }

    openComprobantePdf(item) {
        const url = this.comprobantePdfUrl(item);
        if (!url) {
            this.notification.add("Este comprobante no tiene TLQV para generar PDF.", {
                type: "warning",
            });
            return;
        }
        this.state.xubio.pdfLoadingTlqv = item.tlqvCode;
        window.open(url, "_blank", "noopener");
        window.setTimeout(() => {
            if (this.state.xubio.pdfLoadingTlqv === item.tlqvCode) {
                this.state.xubio.pdfLoadingTlqv = "";
            }
        }, 1200);
    }

    comprobantePdfUrl(item) {
        const tlqvCode = String(item?.tlqvCode || "").trim();
        if (!tlqvCode) {
            return "";
        }
        return `/lqa_admin_panel/accounting/comprobantes/${encodeURIComponent(
            tlqvCode
        )}/cdn`;
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

    formatDateOnly(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
            dateStyle: "short",
        }).format(date);
    }

    formatBool(value) {
        return value ? "Si" : "No";
    }

    downloadBase64File(filename, content, mimetype) {
        const anchor = document.createElement("a");
        anchor.href = `data:${mimetype || "application/octet-stream"};base64,${content}`;
        anchor.download = filename || "xubio-comprobantes.xlsx";
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
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
