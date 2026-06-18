/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MARKETPLACES = [
    {
        id: "fravega",
        name: "Fravega",
        logo: "/lqa_admin_panel/static/src/img/marketplace/fravega.png?v=1",
    },
    {
        id: "megatone",
        name: "Megatone",
        logo: "/lqa_admin_panel/static/src/img/marketplace/megatone.svg?v=1",
    },
    {
        id: "oncity",
        name: "OnCity",
        logo: "/lqa_admin_panel/static/src/img/marketplace/oncity.png?v=1",
    },
];

export class LqaRetailersPublisherExecute extends Component {
    static template = "lqa_admin_panel.RetailersPublisherExecute";

    setup() {
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            folders: [],
            marketplaces: MARKETPLACES,
            selectedFolderId: "",
            selectedMarketplaces: {
                fravega: true,
                megatone: true,
                oncity: true,
            },
            loadingFolders: true,
            executing: false,
            confirmExecution: false,
            result: null,
        });

        onWillStart(async () => {
            await this.loadFolders();
        });
    }

    get selectedFolder() {
        return this.state.folders.find(
            (folder) => String(folder.id) === String(this.state.selectedFolderId)
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

    async loadFolders() {
        this.state.loadingFolders = true;
        try {
            const folders = await this.orm.call(
                "lqa.retailers.publisher.service",
                "get_folders",
                []
            );
            this.state.folders = folders || [];
            if (
                !this.state.folders.some(
                    (folder) =>
                        String(folder.id) === String(this.state.selectedFolderId)
                )
            ) {
                this.state.selectedFolderId = this.state.folders.length
                    ? String(this.state.folders[0].id)
                    : "";
            }
        } catch (error) {
            this.notifyError(error, "No se pudieron cargar las carpetas de Madre.");
        } finally {
            this.state.loadingFolders = false;
        }
    }

    toggleMarketplace(marketplace) {
        this.state.selectedMarketplaces[marketplace.id] =
            !this.state.selectedMarketplaces[marketplace.id];
    }

    openExecutionConfirmation() {
        if (!this.selectedFolder) {
            this.notification.add("Selecciona una carpeta.", { type: "warning" });
            return;
        }
        if (!this.selectedMarketplaceIds.length) {
            this.notification.add("Selecciona al menos un marketplace.", {
                type: "warning",
            });
            return;
        }
        this.state.confirmExecution = true;
    }

    closeExecutionConfirmation() {
        if (!this.state.executing) {
            this.state.confirmExecution = false;
        }
    }

    async confirmExecutePublication() {
        if (!this.selectedFolder || !this.selectedMarketplaceIds.length) {
            return;
        }
        this.state.executing = true;
        try {
            const result = await this.orm.call(
                "lqa.retailers.publisher.service",
                "execute_publication",
                [this.selectedFolder.id, this.selectedMarketplaceIds]
            );
            this.state.result = result;
            if (result.run_id) {
                window.sessionStorage.setItem("lqaPublisherRunId", result.run_id);
            }
            this.state.confirmExecution = false;
            this.notification.add("Publication run creado correctamente.", {
                type: "success",
            });
        } catch (error) {
            this.notifyError(error, "No se pudo ejecutar la publicacion.");
        } finally {
            this.state.executing = false;
        }
    }

    isMarketplaceSelected(marketplace) {
        return Boolean(this.state.selectedMarketplaces[marketplace.id]);
    }

    marketplaceName(marketplaceId) {
        return (
            this.state.marketplaces.find(
                (marketplace) => marketplace.id === marketplaceId
            )?.name || marketplaceId
        );
    }

    statusLabel(value) {
        return (
            {
                QUEUED: "En cola",
                PENDING: "Pendiente",
                STARTED: "Iniciado",
                PROCESSING: "Procesando",
                SUCCESS: "Correcto",
                COMPLETED: "Completado",
                FAILED: "Fallido",
                ERROR: "Error",
            }[String(value || "").toUpperCase()] || value || "En cola"
        );
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
        "lqa_admin_panel.retailers_publisher_execute",
        LqaRetailersPublisherExecute
    );
