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
            selectionFolders: [],
            selectedFolderId: "",
            folderImport: null,
            startingFolderImport: false,
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

    async loadJob(jobId, showLoader = true) {
        if (!jobId) {
            this.state.selectedJob = null;
            return;
        }
        if (showLoader) {
            this.state.loadingJob = true;
        }
        try {
            this.state.selectedJob = await this.orm.call(
                "lqa.mercadolibre.pricing.service",
                "get_job",
                [Number(jobId)]
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
            const previousState = this.state.folderImport?.state;
            this.state.folderImport = importJob || null;
            if (
                showNotification &&
                importJob?.state === "done" &&
                previousState &&
                previousState !== "done"
            ) {
                this.notification.add(
                    `Carpeta preparada: ${this.formatNumber(importJob.jobs)} jobs creados.`,
                    { type: "success" }
                );
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
                "La carpeta se está dividiendo en jobs de pricing de hasta 5.000 publicaciones.",
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
