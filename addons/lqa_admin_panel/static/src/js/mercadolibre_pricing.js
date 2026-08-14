/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MANUAL_TEMPLATE = `mla,sku,tipo_publicacion,precio,categoria,meliContributionPercentage
MLA2228742950,B0F47N62NN,gold_special,731399,MLA31040,2.4
MLA987654321,SKU456,gold_pro,85000,MLA410558,`;
const MAX_DIRECT_CSV_BYTES = 10 * 1024 * 1024;

export class LqaMercadolibrePricing extends Component {
    static template = "lqa_admin_panel.MercadolibrePricing";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.refreshTimer = null;
        this.state = useState({
            csvName: "",
            csvContent: "",
            manualText: MANUAL_TEMPLATE,
            jobs: [],
            selectedJobId: "",
            selectedJob: null,
            loadingJobs: true,
            loadingJob: false,
            creatingCsv: false,
            creatingManual: false,
            downloadingJobId: "",
            retryingJobId: "",
            selectionFolders: [],
            selectedFolderId: "",
            folderImport: null,
            startingFolderImport: false,
            generatingFolderExcel: false,
            retryingFolderImport: false,
            jobLineOffset: 0,
            jobLineLimit: 200,
        });

        onWillStart(async () => {
            await Promise.all([
                this.loadJobs(),
                this.loadSelectionFolders(),
                this.loadFolderImport(),
            ]);
        });

        onMounted(() => {
            this.refreshTimer = window.setInterval(
                () => this.refreshWorkspace(),
                10000
            );
        });

        onWillUnmount(() => {
            if (this.refreshTimer) {
                window.clearInterval(this.refreshTimer);
            }
        });
    }

    get selectedJobFromList() {
        return this.state.jobs.find(
            (job) => String(job.id) === String(this.state.selectedJobId)
        );
    }

    async loadJobs(showLoader = true) {
        if (showLoader) {
            this.state.loadingJobs = true;
        }
        try {
            this.state.jobs = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "get_jobs",
                [30]
            );
            if (
                this.state.selectedJobId &&
                !this.state.jobs.some(
                    (job) => String(job.id) === String(this.state.selectedJobId)
                )
            ) {
                this.state.selectedJobId = "";
                this.state.selectedJob = null;
            }
            if (!this.state.selectedJobId && this.state.jobs.length) {
                this.state.selectedJobId = String(this.state.jobs[0].id);
            }
            if (this.state.selectedJobId) {
                await this.loadJob(this.state.selectedJobId, false);
            }
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudieron cargar los jobs de pricing.",
                { type: "danger" }
            );
        } finally {
            this.state.loadingJobs = false;
        }
    }

    async loadJob(jobId, showLoader = true, offset = null) {
        if (!jobId) {
            this.state.selectedJob = null;
            return;
        }
        if (showLoader) {
            this.state.loadingJob = true;
        }
        const isNewJob = String(jobId) !== String(this.state.selectedJobId);
        if (isNewJob) {
            this.state.jobLineOffset = 0;
        } else if (offset !== null) {
            this.state.jobLineOffset = Math.max(Number(offset) || 0, 0);
        }
        try {
            this.state.selectedJob = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "get_job",
                [
                    Number(jobId),
                    this.state.jobLineLimit,
                    this.state.jobLineOffset,
                ]
            );
            this.state.selectedJobId = String(jobId);
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo cargar el job.",
                { type: "danger" }
            );
        } finally {
            this.state.loadingJob = false;
        }
    }

    async onCsvSelected(event) {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }
        if (file.size > MAX_DIRECT_CSV_BYTES) {
            event.target.value = "";
            this.notification.add(
                "Este CSV es demasiado grande para la carga directa. Elegí la carpeta guardada en la sección 'Desde Selecciones'.",
                { type: "warning" }
            );
            return;
        }
        this.state.csvName = file.name;
        this.state.csvContent = await file.text();
        event.target.value = "";
        this.notification.add(`Archivo listo: ${file.name}`, { type: "success" });
    }

    async refreshWorkspace() {
        await Promise.all([this.loadJobs(false), this.loadFolderImport(false)]);
    }

    async loadSelectionFolders() {
        try {
            this.state.selectionFolders = await this.orm.call(
                "lqa.mercadolibre.catalog.service",
                "get_selection_folders",
                []
            );
            if (!this.state.selectedFolderId && this.state.selectionFolders.length) {
                this.state.selectedFolderId = String(this.state.selectionFolders[0].id);
            }
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudieron cargar las carpetas guardadas.",
                { type: "danger" }
            );
        }
    }

    async loadFolderImport(showNotification = true) {
        try {
            const importJob = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "get_active_folder_import",
                []
            );
            const previousState = this.state.folderImport?.pricingState;
            const previousExportState = this.state.folderImport?.exportState;
            this.state.folderImport = importJob || null;
            if (
                showNotification &&
                importJob?.pricingState === "done" &&
                previousState &&
                previousState !== "done"
            ) {
                this.notification.add(
                    `Proceso finalizado: ${this.formatNumber(importJob.success)} publicaciones listas.`,
                    { type: "success" }
                );
            }
            if (
                showNotification &&
                importJob?.exportState === "done" &&
                previousExportState &&
                previousExportState !== "done"
            ) {
                this.notification.add("El Excel consolidado está listo para descargar.", {
                    type: "success",
                });
            }
        } catch (error) {
            if (showNotification) {
                this.notification.add(
                    error?.data?.message || "No se pudo consultar la importación.",
                    { type: "danger" }
                );
            }
        }
    }

    async startFolderImport() {
        if (!this.state.selectedFolderId) {
            this.notification.add("Elegí una carpeta de Selecciones.", {
                type: "warning",
            });
            return;
        }
        this.state.startingFolderImport = true;
        try {
            this.state.folderImport = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "start_selection_folder_import",
                [Number(this.state.selectedFolderId)]
            );
            this.notification.add(
                "El procesamiento masivo comenzó. La pantalla mostrará un único proceso.",
                { type: "info" }
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo iniciar el procesamiento de la carpeta.",
                { type: "danger" }
            );
        } finally {
            this.state.startingFolderImport = false;
        }
    }

    get folderImportProgress() {
        const total = Number(this.state.folderImport?.total || 0);
        const processed = Number(this.state.folderImport?.processed || 0);
        return total ? Math.min(Math.round((processed / total) * 100), 100) : 0;
    }

    get isFolderImportRunning() {
        return ["queued", "running"].includes(this.state.folderImport?.state);
    }

    get folderPricingProgress() {
        const total = Number(this.state.folderImport?.jobs || 0);
        const completed = Number(this.state.folderImport?.completedJobs || 0);
        return total ? Math.min(Math.round((completed / total) * 100), 100) : 0;
    }

    async generateFolderExcel() {
        const importJob = this.state.folderImport;
        if (!importJob?.id) {
            return;
        }
        this.state.generatingFolderExcel = true;
        try {
            this.state.folderImport = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "start_folder_import_export",
                [importJob.id]
            );
            this.notification.add(
                "Estamos generando un único Excel con todo el resultado.",
                { type: "info" }
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo generar el Excel consolidado.",
                { type: "danger" }
            );
        } finally {
            this.state.generatingFolderExcel = false;
        }
    }

    async retryFolderImport() {
        const importJob = this.state.folderImport;
        if (!importJob?.id) {
            return;
        }
        this.state.retryingFolderImport = true;
        try {
            this.state.folderImport = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "retry_failed_folder_jobs",
                [importJob.id]
            );
            this.notification.add(
                "Los lotes con error volvieron a la cola.",
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudieron reintentar los errores.",
                { type: "danger" }
            );
        } finally {
            this.state.retryingFolderImport = false;
        }
    }

    downloadFolderExcel() {
        if (!this.state.folderImport?.downloadUrl) {
            return;
        }
        const anchor = document.createElement("a");
        anchor.href = this.state.folderImport.downloadUrl;
        anchor.download = "";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
    }

    previousJobLines() {
        const pagination = this.state.selectedJob?.linePagination;
        if (pagination?.hasPrevious) {
            this.loadJob(
                this.state.selectedJobId,
                true,
                Math.max(pagination.offset - pagination.limit, 0)
            );
        }
    }

    nextJobLines() {
        const pagination = this.state.selectedJob?.linePagination;
        if (pagination?.hasNext) {
            this.loadJob(
                this.state.selectedJobId,
                true,
                pagination.offset + pagination.limit
            );
        }
    }

    clearCsv() {
        this.state.csvName = "";
        this.state.csvContent = "";
    }

    async submitCsv() {
        if (!this.state.csvContent) {
            this.notification.add("Selecciona un CSV para procesar.", {
                type: "warning",
            });
            return;
        }
        this.state.creatingCsv = true;
        try {
            const job = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "create_job",
                ["csv", this.state.csvContent, this.state.csvName]
            );
            this.clearCsv();
            await this.loadJobs(false);
            await this.loadJob(job.id);
            this.notification.add("Job de pricing creado. Se procesa en segundo plano.", {
                type: "success",
            });
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo crear el job desde CSV.",
                { type: "danger" }
            );
        } finally {
            this.state.creatingCsv = false;
        }
    }

    async submitManual() {
        if (!String(this.state.manualText || "").trim()) {
            this.notification.add("Pega filas CSV o JSON para procesar.", {
                type: "warning",
            });
            return;
        }
        this.state.creatingManual = true;
        try {
            const job = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "create_job",
                ["manual", this.state.manualText, ""]
            );
            await this.loadJobs(false);
            await this.loadJob(job.id);
            this.notification.add("Job manual creado. Se procesa en segundo plano.", {
                type: "success",
            });
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo crear el job manual.",
                { type: "danger" }
            );
        } finally {
            this.state.creatingManual = false;
        }
    }

    async downloadJobXlsx(job) {
        this.state.downloadingJobId = String(job.id);
        try {
            const result = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "download_job_xlsx",
                [job.id]
            );
            this.downloadBase64File(
                result.filename,
                result.content,
                result.mimetype
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo descargar el Excel.",
                { type: "danger" }
            );
        } finally {
            this.state.downloadingJobId = "";
        }
    }

    async retryJob(job) {
        this.state.retryingJobId = String(job.id);
        try {
            await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "retry_job",
                [job.id]
            );
            await this.loadJobs(false);
            this.notification.add(
                "El job volvió a la cola y se procesará en lotes de 50.",
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo reintentar el job.",
                { type: "danger" }
            );
        } finally {
            this.state.retryingJobId = "";
        }
    }

    isRetryingJob(job) {
        return String(job?.id) === String(this.state.retryingJobId);
    }

    downloadBase64File(filename, content, mimetype) {
        const binary = window.atob(content || "");
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index++) {
            bytes[index] = binary.charCodeAt(index);
        }
        const blob = new Blob([bytes], {
            type:
                mimetype ||
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename || "mercadolibre-pricing.xlsx";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    }

    isSelectedJob(job) {
        return String(job.id) === String(this.state.selectedJobId);
    }

    isDownloading(job) {
        return String(job.id) === String(this.state.downloadingJobId);
    }

    canDownload(job) {
        return ["done", "failed"].includes(job.state);
    }

    stateLabel(state) {
        return (
            {
                pending: "En cola",
                processing: "Procesando",
                preparing: "Preparando lotes",
                running: "Procesando",
                queued: "En cola",
                done: "Listo",
                failed: "Error",
            }[state] || state
        );
    }

    formatDateTime(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(`${value}Z`);
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

    formatCurrency(value, currency = "ARS") {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "-";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency,
            maximumFractionDigits: 0,
        }).format(numericValue);
    }

    formatNumber(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return "0";
        }
        return new Intl.NumberFormat("es-AR").format(numericValue);
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.mercadolibre_pricing", LqaMercadolibrePricing);
