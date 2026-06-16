/** @odoo-module **/

const BRAND_NAME = "Tienda Lo Quiero Aca";
const DEFAULT_TITLE = `Panel Comercial - ${BRAND_NAME}`;
const ICON_HREF = "/lqa_admin_panel/static/src/img/tienda-logo-app.png?v=3";

function upsertIcon(rel, type) {
    let link = document.head.querySelector(`link[rel="${rel}"]`);
    if (!link) {
        link = document.createElement("link");
        link.rel = rel;
        document.head.appendChild(link);
    }
    link.href = ICON_HREF;
    if (type) {
        link.type = type;
    }
}

function applyBranding() {
    upsertIcon("icon", "image/png");
    upsertIcon("shortcut icon", "image/png");
    upsertIcon("apple-touch-icon");

    const title = document.title || "";
    if (!title || title === "Odoo") {
        document.title = DEFAULT_TITLE;
    } else if (!title.includes(BRAND_NAME)) {
        document.title = `${title} - ${BRAND_NAME}`;
    }
}

applyBranding();
window.addEventListener("hashchange", applyBranding);
window.addEventListener("popstate", applyBranding);
setInterval(applyBranding, 2000);
