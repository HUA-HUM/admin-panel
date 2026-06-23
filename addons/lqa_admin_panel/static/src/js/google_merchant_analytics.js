/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const toInputDate = (date) => date.toISOString().slice(0, 10);

const defaultDates = () => {
    const today = new Date();
    const from = new Date(today);
    from.setDate(today.getDate() - 7);
    return {
        from: toInputDate(from),
        to: toInputDate(today),
    };
};

export class LqaGoogleMerchantAnalytics extends Component {
    static template = "lqa_admin_panel.GoogleMerchantAnalytics";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        const dates = defaultDates();
        this.state = useState({
            form: {
                sku: "",
                from: dates.from,
                to: dates.to,
            },
            loadingQuery: false,
            loadingHistory: true,
            current: null,
            history: [],
            expandedResponses: {},
        });

        onWillStart(async () => {
            await this.loadHistory();
        });
    }

    get canQuery() {
        return Boolean(
            this.state.form.sku.trim() &&
                this.state.form.from &&
                this.state.form.to &&
                !this.state.loadingQuery
        );
    }

    get selectedRecord() {
        return this.state.current || this.state.history[0] || null;
    }

    get selectedRows() {
        const rows = this.selectedRecord?.rows;
        return Array.isArray(rows) ? rows : [];
    }

    get maxChartValue() {
        return Math.max(
            1,
            ...this.selectedRows.map((row) =>
                Math.max(this.rowClicks(row), this.rowImpressions(row))
            )
        );
    }

    async queryPerformance() {
        if (!this.canQuery) {
            this.notification.add("Completá SKU, fecha desde y fecha hasta.", {
                type: "warning",
            });
            return;
        }
        this.state.loadingQuery = true;
        try {
            const result = await this.orm.call(
                "lqa.google.merchant.analytics.service",
                "query_performance",
                [
                    {
                        sku: this.state.form.sku,
                        from: this.state.form.from,
                        to: this.state.form.to,
                    },
                ]
            );
            this.state.current = result;
            await this.loadHistory(false);
            this.notification.add(
                `Consulta guardada para ${result.sku}: ${this.formatNumber(
                    result.clicks
                )} clicks.`,
                { type: "success" }
            );
        } catch (error) {
            await this.loadHistory(false);
            this.notifyError(error, "No se pudo consultar performance.");
        } finally {
            this.state.loadingQuery = false;
        }
    }

    async loadHistory(showLoading = true) {
        if (showLoading) {
            this.state.loadingHistory = true;
        }
        try {
            this.state.history = await this.orm.call(
                "lqa.google.merchant.analytics.service",
                "get_history",
                [80]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el historial de analytics.");
        } finally {
            this.state.loadingHistory = false;
        }
    }

    selectRecord(record) {
        this.state.current = record;
        this.state.form.sku = record.sku || "";
        this.state.form.from = record.from || this.state.form.from;
        this.state.form.to = record.to || this.state.form.to;
    }

    toggleResponse(record) {
        this.state.expandedResponses[record.id] =
            !this.state.expandedResponses[record.id];
    }

    statusLabel(value) {
        return (
            {
                completed: "Completado",
                failed: "Fallido",
            }[String(value || "").toLowerCase()] || value || "-"
        );
    }

    rowDate(row) {
        return (
            row?.date ||
            row?.day ||
            row?.fecha ||
            row?.period ||
            row?.segments?.date ||
            "-"
        );
    }

    rowClicks(row) {
        return this.asNumber(row?.clicks || row?.metrics?.clicks || 0);
    }

    rowImpressions(row) {
        return this.asNumber(
            row?.impressions || row?.metrics?.impressions || row?.views || 0
        );
    }

    rowCtr(row) {
        return this.asNumber(
            row?.clickThroughRate ||
                row?.ctr ||
                row?.metrics?.clickThroughRate ||
                row?.metrics?.ctr ||
                0
        );
    }

    barWidth(value) {
        return `${Math.max(2, Math.round((this.asNumber(value) / this.maxChartValue) * 100))}%`;
    }

    formatNumber(value) {
        return new Intl.NumberFormat("es-AR").format(this.asNumber(value));
    }

    formatPercent(value) {
        const number = this.asNumber(value);
        const percent = number > 1 ? number : number * 100;
        return `${new Intl.NumberFormat("es-AR", {
            maximumFractionDigits: 2,
        }).format(percent)}%`;
    }

    formatDate(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(`${value}T00:00:00`);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        }).format(date);
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

    asNumber(value) {
        const number = Number(value || 0);
        return Number.isFinite(number) ? number : 0;
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
        "lqa_admin_panel.google_merchant_analytics",
        LqaGoogleMerchantAnalytics
    );
