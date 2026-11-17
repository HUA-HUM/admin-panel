/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// products-api hoy acepta solo "fravega": cualquier otro canal responde 400 y
// el backend del panel ya los descartaba en silencio. Mostrar Megatone y
// OnCity tildados hacia creer que se publicaba en tres lugares.
const MARKETPLACES = [
    {
        id: "fravega",
        name: "Fravega",
        logo: "/lqa_admin_panel/static/src/img/marketplace/fravega.png?v=1",
    },
];

// Fravega procesa como maximo 30 SKUs por minuto (guia de products-api).
const FRAVEGA_SKUS_PER_MINUTE = 30;

export class LqaRetailersPublisherExecute extends Component {
    static template = "lqa_admin_panel.RetailersPublisherExecute";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            folders: [],
            marketplaces: MARKETPLACES,
            // Carpetas abre esta vista con la carpeta ya elegida.
            selectedFolderId: String(
                this.props.action?.context?.lqa_publisher_folder_id || ""
            ),
            selectedMarketplaces: { fravega: true },
            folderQuery: "",
            loadingFolders: true,
            loadingHistory: true,
            executing: false,
            confirmExecution: false,
            history: [],
        });

        // Sin await: la vista se dibuja al instante con su estado de carga y los
        // datos llegan despues. Esperarlos dejaba congelada la pantalla anterior
        // (con el overlay de carga) hasta que respondia el servidor.
        onWillStart(() => {
            this.lqaInitialLoad = (async () => {
                await Promise.all([this.loadFolders(), this.loadPublicationHistory()]);
            })();
        });
    }

    get selectedFolder() {
        return this.state.folders.find(
            (folder) => String(folder.id) === String(this.state.selectedFolderId)
        );
    }

    get filteredFolders() {
        const query = this.state.folderQuery.trim().toLowerCase();
        if (!query) {
            return this.state.folders;
        }
        return this.state.folders.filter(
            (folder) =>
                String(folder.name || "").toLowerCase().includes(query) ||
                String(folder.id) === query.replace(/^#/, "")
        );
    }

    get selectedMarketplaceIds() {
        return this.state.marketplaces
            .filter((marketplace) => this.state.selectedMarketplaces[marketplace.id])
            .map((marketplace) => marketplace.id);
    }

    get selectedMarketplaceNames() {
        return this.state.marketplaces
            .filter((marketplace) => this.state.selectedMarketplaces[marketplace.id])
            .map((marketplace) => marketplace.name)
            .join(", ");
    }

    get estimatedJobs() {
        const count = this.selectedFolder?.product_count;
        if (count === null || count === undefined) {
            return null;
        }
        return count * this.selectedMarketplaceIds.length;
    }

    get canPublish() {
        return Boolean(
            this.selectedFolder &&
                this.selectedFolder.product_count !== 0 &&
                this.selectedMarketplaceIds.length &&
                !this.state.executing
        );
    }

    // Piso, no promesa: cada SKU consulta a OpenAI y procesa imagenes, asi que
    // en la practica tarda mas.
    get estimatedDuration() {
        const skus = this.selectedFolder?.product_count;
        if (!skus) {
            return "";
        }
        const minutes = Math.ceil(skus / FRAVEGA_SKUS_PER_MINUTE);
        if (minutes < 60) {
            return `al menos ${minutes} min`;
        }
        const hours = Math.floor(minutes / 60);
        const rest = minutes % 60;
        return rest ? `al menos ${hours} h ${rest} min` : `al menos ${hours} h`;
    }

    async loadFolders() {
        this.state.loadingFolders = true;
        try {
            // Sin conteos: las carpetas se ven enseguida y los numeros llegan
            // aparte (una consulta a madre por carpeta).
            const folders = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_folders",
                [false]
            );
            this.state.folders = folders || [];
            if (!this.selectedFolder && this.state.folders.length) {
                this.state.selectedFolderId = String(this.state.folders[0].id);
            }
            this.loadFolderCounts();
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar las carpetas de Madre.");
        } finally {
            this.state.loadingFolders = false;
        }
    }

    async loadFolderCounts() {
        const ids = this.state.folders.map((folder) => folder.id);
        if (!ids.length) {
            return;
        }
        try {
            const counts = await this.orm.silent.call(
                "lqa.retailers.publisher.service",
                "get_folder_counts",
                [ids]
            );
            for (const folder of this.state.folders) {
                const count = counts?.[String(folder.id)];
                if (count !== undefined) {
                    folder.product_count = count;
                }
            }
            // Si la elegida por defecto resulto vacia, pasar a una con productos.
            if (this.selectedFolder?.product_count === 0) {
                const withProducts = this.state.folders.find((folder) => folder.product_count);
                if (withProducts) {
                    this.state.selectedFolderId = String(withProducts.id);
                }
            }
        } catch {
            // Sin conteos se puede elegir igual: el resumen muestra un guion.
        }
    }

    async loadPublicationHistory() {
        this.state.loadingHistory = true;
        try {
            this.state.history = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_publication_history",
                [20]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo cargar el historial de publicaciones.");
        } finally {
            this.state.loadingHistory = false;
        }
    }

    selectFolder(folder) {
        this.state.selectedFolderId = String(folder.id);
    }

    isSelectedFolder(folder) {
        return String(folder.id) === String(this.state.selectedFolderId);
    }

    toggleMarketplace(marketplace) {
        this.state.selectedMarketplaces[marketplace.id] =
            !this.state.selectedMarketplaces[marketplace.id];
    }

    isMarketplaceSelected(marketplace) {
        return Boolean(this.state.selectedMarketplaces[marketplace.id]);
    }

    openExecutionConfirmation() {
        if (this.canPublish) {
            this.state.confirmExecution = true;
        }
    }

    closeExecutionConfirmation() {
        if (!this.state.executing) {
            this.state.confirmExecution = false;
        }
    }

    async confirmExecutePublication() {
        if (!this.canPublish) {
            return;
        }
        // products-api tarda mas cuanto mas grande es la carpeta (lee todo y
        // crea los jobs de a 500): el boton queda bloqueado para no lanzar dos.
        this.state.executing = true;
        let result = null;
        try {
            result = await this.orm.call(
                "lqa.retailers.publisher.service",
                "execute_publication",
                [this.selectedFolder.id, this.selectedMarketplaceIds]
            );
        } catch (error) {
            this.notifyError(error, "No se pudo ejecutar la publicación.");
        } finally {
            this.state.executing = false;
            this.state.confirmExecution = false;
        }
        if (!result) {
            return;
        }
        if (!result.ok || !result.run_id) {
            // Un 500 puede dejar el run a medias: no se reintenta solo porque
            // se duplicarian los jobs.
            this.notification.add(
                result.message ||
                    "La publicación no pudo crearse. Revisá el historial antes de reintentar.",
                { type: "danger", sticky: true }
            );
            await this.loadPublicationHistory();
            return;
        }
        this.notification.add(
            `Publicación #${result.run_id} en marcha: ${this.formatNumber(result.jobs_count)} SKU encolados.`,
            { type: "success" }
        );
        this.openTracking(result.run_id);
    }

    openTracking(runId) {
        if (!runId) {
            return;
        }
        this.action.doAction("lqa_admin_panel.action_lqa_retailers_publisher_tracking", {
            additionalContext: { lqa_publisher_run_id: String(runId) },
        });
    }

    folderName(folderId) {
        const folder = this.state.folders.find(
            (item) => String(item.id) === String(folderId)
        );
        return folder ? folder.name : `Carpeta #${folderId}`;
    }

    folderExists(folderId) {
        return this.state.folders.some((item) => String(item.id) === String(folderId));
    }

    marketplaceName(marketplaceId) {
        return (
            {
                fravega: "Fravega",
                megatone: "Megatone",
                oncity: "OnCity",
            }[String(marketplaceId || "").toLowerCase()] || marketplaceId
        );
    }

    isHistoryError(execution) {
        return ["ERROR", "FAILED"].includes(String(execution.status || "").toUpperCase());
    }

    formatCount(value) {
        return value === null || value === undefined ? "—" : this.formatNumber(value);
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
        // Odoo guarda UTC sin zona ("2026-11-17 18:19:26"): sin la Z, el
        // navegador lo leeria como hora local y quedaria corrido tres horas.
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

    notifyError(error, fallback) {
        this.notification.add(error?.data?.message || fallback, {
            type: "danger",
        });
    }
}

registry
    .category("actions")
    .add("lqa_admin_panel.retailers_publisher_execute", LqaRetailersPublisherExecute);
