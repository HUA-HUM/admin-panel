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
        const today = new Date();
        const currentMonthStart = new Date(today.getFullYear(), today.getMonth(), 1);
        const inputDate = (date) =>
            [
                date.getFullYear(),
                String(date.getMonth() + 1).padStart(2, "0"),
                String(date.getDate()).padStart(2, "0"),
            ].join("-");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            view: params.view || "dashboard",
            activeTab:
                params.view === "arca_billing"
                    ? "comprobantes"
                    : params.view === "xubio_facturacion"
                    ? "facturacion"
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
                activeTab: "list",
                loading: false,
                exporting: false,
                showExportFields: false,
                exportColumns: [],
                pdfLoadingTlqv: "",
                backfill: {
                    running: false,
                    result: null,
                    form: {
                        fechaDesde: inputDate(currentMonthStart),
                        fechaHasta: inputDate(today),
                        batchSize: 10,
                        windowSizeDays: 1,
                        xubioLimit: 100,
                    },
                },
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
            facturacion: {
                activeTab: "create",
                creationMode: "single",
                invoice: {
                    running: false,
                    loadingJobs: false,
                    jobs: [],
                    selectedJob: null,
                    form: {
                        tlqvCode: "",
                        issueDate: inputDate(today),
                        dryRun: true,
                        note: "",
                    },
                },
                bulk: {
                    running: false,
                    result: null,
                    form: {
                        tlqvCodes: "",
                        issueDate: inputDate(today),
                        dryRun: true,
                    },
                },
                cache: {
                    running: false,
                    result: null,
                    form: {
                        pageSize: 100,
                    },
                },
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

    get isXubioFacturacion() {
        return this.state.view === "xubio_facturacion";
    }

    get isWorkspace() {
        return this.isArcaBilling || this.isClients || this.isXubio || this.isXubioFacturacion;
    }

    get pageTitle() {
        if (this.isClients) {
            return "Clientes";
        }
        if (this.isXubio) {
            return "Xubio";
        }
        if (this.isXubioFacturacion) {
            return "Facturacion Xubio";
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
        if (this.isXubioFacturacion) {
            return "Creacion de facturas conectada a Xubio.";
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
        if (this.isClients || this.isArcaBilling || this.isXubioFacturacion) {
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

    async openXubioFacturacion() {
        this.state.view = "xubio_facturacion";
        this.state.activeTab = "facturacion";
        await this.loadArcaData();
    }

    async loadArcaData() {
        if (this.isClients) {
            await Promise.all([this.loadClientJobs(), this.searchClientIssues()]);
            return;
        }
        if (this.isArcaBilling) {
            await Promise.all([this.loadXubioExportColumns(), this.searchComprobantes()]);
            return;
        }
        if (this.isXubioFacturacion && this.state.facturacion.activeTab === "create") {
            await this.loadInvoiceCreationJobs(
                this.state.facturacion.invoice.selectedJob?.id || false
            );
        }
    }

    setTab(tab) {
        this.state.activeTab = tab;
        this.state.view =
            tab === "comprobantes"
                ? "arca_billing"
                : tab === "xubio"
                ? "xubio"
                : tab === "facturacion"
                ? "xubio_facturacion"
                : "clients";
        this.loadArcaData();
    }

    setComprobantesTab(tab) {
        this.state.xubio.activeTab = tab;
        if (tab === "list") {
            this.loadArcaData();
        }
    }

    async setFacturacionTab(tab) {
        this.state.facturacion.activeTab = tab;
        if (tab === "create") {
            await this.loadInvoiceCreationJobs(
                this.state.facturacion.invoice.selectedJob?.id || false
            );
        }
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

    async runXubioBackfillNow() {
        const form = this.state.xubio.backfill.form;
        if (!form.fechaDesde || !form.fechaHasta) {
            this.notification.add("Completa fecha desde y fecha hasta.", {
                type: "warning",
            });
            return;
        }
        this.state.xubio.backfill.running = true;
        this.state.xubio.backfill.result = null;
        try {
            const result = await this.orm.call(
                "lqa.accounting.service",
                "run_xubio_comprobantes_backfill_now",
                [
                    {
                        fechaDesde: form.fechaDesde,
                        fechaHasta: form.fechaHasta,
                        batchSize: Number(form.batchSize || 10),
                        windowSizeDays: Number(form.windowSizeDays || 1),
                        xubioLimit: Number(form.xubioLimit || 100),
                    },
                ]
            );
            this.state.xubio.backfill.result = result;
            this.notification.add("Backfill de comprobantes ejecutado.", {
                type: "success",
            });
            await this.searchComprobantes();
        } catch (error) {
            this.notifyError(error, "No se pudo ejecutar el backfill de comprobantes.");
        } finally {
            this.state.xubio.backfill.running = false;
        }
    }

    async runXubioTlqvCacheRefresh() {
        const form = this.state.facturacion.cache.form;
        const pageSize = Number(form.pageSize || 100);
        if (!Number.isFinite(pageSize) || pageSize < 1) {
            this.notification.add("Page size debe ser mayor a cero.", {
                type: "warning",
            });
            return;
        }

        this.state.facturacion.cache.running = true;
        this.state.facturacion.cache.result = null;
        try {
            const result = await this.orm.call(
                "lqa.accounting.service",
                "refresh_xubio_stock_bue_tlqv_cache",
                [{ pageSize }]
            );
            this.state.facturacion.cache.result = result;
            const jobId = result?.payload?.jobId || result?.jobId || "";
            this.notification.add(
                `Actualizacion de cache TLQV encolada${jobId ? `: job ${jobId}` : ""}.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo actualizar el cache TLQV.");
        } finally {
            this.state.facturacion.cache.running = false;
        }
    }

    setInvoiceDryRun(value) {
        this.state.facturacion.invoice.form.dryRun = Boolean(value);
    }

    setInvoiceCreationMode(mode) {
        this.state.facturacion.creationMode = mode === "bulk" ? "bulk" : "single";
    }

    setBulkInvoiceDryRun(value) {
        this.state.facturacion.bulk.form.dryRun = Boolean(value);
    }

    get bulkInvoiceCodes() {
        const matches = String(this.state.facturacion.bulk.form.tlqvCodes || "")
            .toUpperCase()
            .match(/TLQV[-\s]?\d+|\b\d+\b/g) || [];
        return matches.map((value) => {
            const digits = value.match(/\d+/)?.[0] || "";
            return `TLQV-${digits}`;
        });
    }

    get bulkInvoiceUniqueCount() {
        return new Set(this.bulkInvoiceCodes).size;
    }

    get bulkInvoiceDuplicatedCount() {
        return this.bulkInvoiceCodes.length - this.bulkInvoiceUniqueCount;
    }

    get latestInvoiceIssueDate() {
        return this.formatInputDate(new Date());
    }

    get earliestInvoiceIssueDate() {
        const date = new Date();
        date.setDate(date.getDate() - 10);
        return this.formatInputDate(date);
    }

    formatInputDate(date) {
        return [
            date.getFullYear(),
            String(date.getMonth() + 1).padStart(2, "0"),
            String(date.getDate()).padStart(2, "0"),
        ].join("-");
    }

    async createInvoicesBulkFromTlqv() {
        const bulk = this.state.facturacion.bulk;
        const tlqvCodes = this.bulkInvoiceCodes;
        if (!tlqvCodes.length) {
            this.notification.add("Ingresa al menos un TLQV para encolar.", {
                type: "warning",
            });
            return;
        }
        if (
            !bulk.form.dryRun &&
            !window.confirm(
                `Encolar ${this.bulkInvoiceUniqueCount} facturas reales en Xubio?`
            )
        ) {
            return;
        }

        bulk.running = true;
        bulk.result = null;
        try {
            const result = await this.orm.call(
                "lqa.accounting.service",
                "create_invoices_bulk_from_tlqv",
                [{
                    tlqvCodes,
                    issueDate: bulk.form.issueDate || "",
                    dryRun: Boolean(bulk.form.dryRun),
                }]
            );
            bulk.result = result;
            const totalQueued = result?.payload?.totalQueued ?? this.bulkInvoiceUniqueCount;
            this.notification.add(
                `${this.formatNumber(totalQueued)} facturas encoladas correctamente.`,
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudieron encolar las facturas.");
        } finally {
            bulk.running = false;
        }
    }

    async copyBulkBatchId() {
        const batchId = this.state.facturacion.bulk.result?.payload?.batchId || "";
        if (!batchId) {
            return;
        }
        try {
            await navigator.clipboard.writeText(batchId);
            this.notification.add("Batch ID copiado.", { type: "success" });
        } catch (_error) {
            this.notification.add("No se pudo copiar el Batch ID.", { type: "warning" });
        }
    }

    selectInvoiceJob(job) {
        this.state.facturacion.invoice.selectedJob = job;
    }

    invoiceModeLabel(job) {
        return job?.dryRun ? "Simulacion" : "Creacion en Xubio";
    }

    async loadInvoiceCreationJobs(preferJobId = false) {
        this.state.facturacion.invoice.loadingJobs = true;
        try {
            const jobs = await this.orm.call(
                "lqa.accounting.service",
                "get_invoice_creation_jobs",
                [30]
            );
            this.state.facturacion.invoice.jobs = jobs;
            const selected =
                (preferJobId && jobs.find((job) => job.id === preferJobId)) ||
                jobs.find((job) => job.id === this.state.facturacion.invoice.selectedJob?.id) ||
                jobs[0] ||
                null;
            this.state.facturacion.invoice.selectedJob = selected;
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar los registros de facturacion.");
        } finally {
            this.state.facturacion.invoice.loadingJobs = false;
        }
    }

    async createInvoiceFromTlqv() {
        const form = this.state.facturacion.invoice.form;
        const tlqvCode = String(form.tlqvCode || "").trim().toUpperCase();
        if (!tlqvCode) {
            this.notification.add("Ingresa un TLQV para crear la factura.", {
                type: "warning",
            });
            return;
        }
        const issueDate = form.issueDate || inputDate(new Date());
        form.issueDate = issueDate;
        if (
            !form.dryRun &&
            !window.confirm(`Crear factura en Xubio para ${tlqvCode}? El flujo se detiene antes de ARCA.`)
        ) {
            return;
        }

        this.state.facturacion.invoice.running = true;
        try {
            const job = await this.orm.call(
                "lqa.accounting.service",
                "create_invoice_from_tlqv",
                [
                    {
                        tlqvCode,
                        issueDate,
                        dryRun: Boolean(form.dryRun),
                        note: form.note || "",
                    },
                ]
            );
            this.state.facturacion.invoice.selectedJob = job;
            await this.loadInvoiceCreationJobs(job.id);
            this.notification.add(
                job.state === "done"
                    ? "Factura procesada."
                    : "La ejecucion termino con observaciones.",
                { type: job.state === "done" ? "success" : "warning" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo crear la factura desde TLQV.");
        } finally {
            this.state.facturacion.invoice.running = false;
        }
    }

    async openComprobantePdf(item) {
        const tlqvCode = this.comprobanteTlqvCode(item);
        if (!tlqvCode) {
            this.notification.add("Este comprobante no tiene TLQV para generar PDF.", {
                type: "warning",
            });
            return;
        }

        const pdfWindow = window.open("about:blank", "_blank");
        if (pdfWindow) {
            pdfWindow.document.write(
                "<!doctype html><title>Generando PDF</title><body style=\"font-family: sans-serif; padding: 24px;\">Generando comprobante...</body>"
            );
        }

        this.state.xubio.pdfLoadingTlqv = tlqvCode;
        try {
            const result = await this.orm.call(
                "lqa.accounting.service",
                "create_tlqv_document_cdn",
                [tlqvCode]
            );
            if (!result?.cdnUrl) {
                throw new Error("Invoice API no devolvio una URL de CDN.");
            }
            if (pdfWindow) {
                pdfWindow.location.href = result.cdnUrl;
            } else {
                window.open(result.cdnUrl, "_blank", "noopener");
            }
        } catch (error) {
            if (pdfWindow) {
                pdfWindow.close();
            }
            this.notifyError(error, "No se pudo generar el PDF en CDN.");
        } finally {
            if (this.state.xubio.pdfLoadingTlqv === tlqvCode) {
                this.state.xubio.pdfLoadingTlqv = "";
            }
        }
    }

    canGenerateComprobantePdf(item) {
        return Boolean(this.comprobanteTlqvCode(item));
    }

    comprobanteTlqvCode(item) {
        return String(item?.tlqvCode || "").trim();
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
        const key = String(value || "").toLowerCase();
        return (
            {
                done: "Listo",
                completed: "Completado",
                partial: "Parcial",
                failed: "Fallido",
                error: "Error",
                blocked: "Bloqueado",
                processing: "Procesando",
                queued: "En cola",
                success: "Creado",
                issue: "Con issue",
                skipped: "Omitido",
            }[key] || this.humanize(value)
        );
    }

    stateClass(value) {
        const key = String(value || "").toLowerCase();
        if (["done", "success", "completed"].includes(key)) {
            return "is-green";
        }
        if (["partial", "issue", "skipped", "queued", "processing"].includes(key)) {
            return "is-amber";
        }
        if (["failed", "error", "blocked"].includes(key)) {
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

    formatJson(value) {
        try {
            return JSON.stringify(value || {}, null, 2);
        } catch (_error) {
            return String(value || "");
        }
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
