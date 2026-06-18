/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LqaRetailersPricing extends Component {
    static template = "lqa_admin_panel.RetailersPricing";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.refreshTimer = null;
        this.fileInput = null;
        this.state = useState({
            manual: {
                sku: "",
                salePrice: "",
                salesChannel: "fravega",
            },
            upload: {
                name: "",
                content: "",
            },
            jobs: [],
            selectedJobId: "",
            selectedJob: null,
            loadingJobs: true,
            loadingJob: false,
            creatingManual: false,
            creatingXlsx: false,
            downloadingTemplate: false,
            downloadingJobId: "",
        });

        onWillStart(async () => {
            await this.loadJobs();
        });
        onMounted(() => {
            this.refreshTimer = window.setInterval(() => this.loadJobs(false), 10000);
        });
        onWillUnmount(() => {
            if (this.refreshTimer) {
                window.clearInterval(this.refreshTimer);
            }
        });
    }

    async loadJobs(showLoader = true) {
        if (showLoader) {
            this.state.loadingJobs = true;
        }
        try {
            this.state.jobs = await this.orm.call(
                "lqa.retailers.pricing.service",
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
            this.notifyError(error, "No se pudieron cargar los jobs de pricing.");
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
                "lqa.retailers.pricing.service",
                "get_job",
                [Number(jobId)]
            );
            this.state.selectedJobId = String(jobId);
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el job.");
        } finally {
            this.state.loadingJob = false;
        }
    }

    async submitManual() {
        if (
            !this.state.manual.sku.trim() ||
            !this.state.manual.salePrice ||
            !this.state.manual.salesChannel
        ) {
            this.notification.add("Completa SKU, precio y canal.", {
                type: "warning",
            });
            return;
        }
        this.state.creatingManual = true;
        try {
            const job = await this.orm.call(
                "lqa.retailers.pricing.service",
                "create_manual_job",
                [
                    this.state.manual.sku,
                    this.state.manual.salePrice,
                    this.state.manual.salesChannel,
                ]
            );
            this.state.manual.sku = "";
            this.state.manual.salePrice = "";
            await this.loadJobs(false);
            await this.loadJob(job.id);
            this.notification.add(
                "Job manual creado. Se procesa en segundo plano.",
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo crear el job manual.");
        } finally {
            this.state.creatingManual = false;
        }
    }

    async onXlsxSelected(event) {
        const file = event.target.files?.[0];
        this.fileInput = event.target;
        if (!file) {
            this.clearUpload();
            return;
        }
        if (!file.name.toLowerCase().endsWith(".xlsx")) {
            this.clearUpload();
            this.notification.add("Selecciona un archivo Excel XLSX.", {
                type: "warning",
            });
            return;
        }
        try {
            const dataUrl = await this.readFileAsDataUrl(file);
            this.state.upload.name = file.name;
            this.state.upload.content = dataUrl.split(",", 2)[1] || "";
        } catch {
            this.clearUpload();
            this.notification.add("No se pudo leer el archivo.", { type: "danger" });
        }
    }

    async submitXlsx() {
        if (!this.state.upload.content) {
            this.notification.add("Selecciona un archivo Excel XLSX.", {
                type: "warning",
            });
            return;
        }
        this.state.creatingXlsx = true;
        try {
            const job = await this.orm.call(
                "lqa.retailers.pricing.service",
                "create_xlsx_job",
                [this.state.upload.name, this.state.upload.content]
            );
            this.clearUpload();
            await this.loadJobs(false);
            await this.loadJob(job.id);
            this.notification.add(
                "Job de pricing creado. Se procesa en segundo plano.",
                { type: "success" }
            );
        } catch (error) {
            this.notifyError(error, "No se pudo crear el job desde Excel.");
        } finally {
            this.state.creatingXlsx = false;
        }
    }

    async downloadTemplate() {
        this.state.downloadingTemplate = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.pricing.service",
                "download_template_xlsx",
                []
            );
            this.downloadBase64File(result.filename, result.content, result.mimetype);
        } catch (error) {
            this.notifyError(error, "No se pudo descargar la plantilla.");
        } finally {
            this.state.downloadingTemplate = false;
        }
    }

    async downloadJobXlsx(job) {
        this.state.downloadingJobId = String(job.id);
        try {
            const result = await this.orm.call(
                "lqa.retailers.pricing.service",
                "download_job_xlsx",
                [job.id]
            );
            this.downloadBase64File(result.filename, result.content, result.mimetype);
        } catch (error) {
            this.notifyError(error, "No se pudo descargar el resultado.");
        } finally {
            this.state.downloadingJobId = "";
        }
    }

    clearUpload() {
        this.state.upload.name = "";
        this.state.upload.content = "";
        if (this.fileInput) {
            this.fileInput.value = "";
        }
    }

    readFileAsDataUrl(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }

    downloadBase64File(filename, content, mimetype) {
        const binary = window.atob(content || "");
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index++) {
            bytes[index] = binary.charCodeAt(index);
        }
        const blob = new Blob([bytes], { type: mimetype });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename || "retailers-pricing.xlsx";
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

    channelLabel(channel) {
        return (
            {
                fravega: "Fravega",
                megatone: "Megatone",
                oncity: "OnCity",
            }[channel] || channel
        );
    }

    profitabilityLabel(line) {
        if (line.state === "failed") {
            return "Error";
        }
        if (line.state !== "done") {
            return "-";
        }
        return line.profitable ? "Rentable" : "No rentable";
    }

    profitabilityClass(line) {
        if (line.state === "failed") {
            return "is-failed";
        }
        if (line.state !== "done") {
            return "is-pending";
        }
        return line.profitable ? "is-profitable" : "is-unprofitable";
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

    formatNumber(value) {
        const numericValue = Number(value);
        return new Intl.NumberFormat("es-AR").format(
            Number.isFinite(numericValue) ? numericValue : 0
        );
    }

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.retailers_pricing", LqaRetailersPricing);
