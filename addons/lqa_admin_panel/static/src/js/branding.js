/** @odoo-module **/

const BRAND_NAME = "Tienda Lo Quiero Aca";
const DEFAULT_TITLE = `Panel Comercial - ${BRAND_NAME}`;
const ICON_HREF = "/lqa_admin_panel/static/src/img/tienda-logo-app.png?v=4";
const MANIFEST_HREF = "/lqa_admin_panel/manifest.webmanifest?v=4";
const THEME_COLOR = "#ff4f5a";

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

function upsertMeta(name, content) {
    let meta = document.head.querySelector(`meta[name="${name}"]`);
    if (!meta) {
        meta = document.createElement("meta");
        meta.name = name;
        document.head.appendChild(meta);
    }
    meta.content = content;
}

function upsertManifest() {
    let link = document.head.querySelector('link[rel="manifest"]');
    if (!link) {
        link = document.createElement("link");
        link.rel = "manifest";
        document.head.appendChild(link);
    }
    link.href = MANIFEST_HREF;
}

function applyBranding() {
    upsertIcon("icon", "image/png");
    upsertIcon("shortcut icon", "image/png");
    upsertIcon("apple-touch-icon");
    upsertManifest();
    upsertMeta("theme-color", THEME_COLOR);
    upsertMeta("application-name", BRAND_NAME);
    upsertMeta("apple-mobile-web-app-title", BRAND_NAME);

    const title = document.title || "";
    const cleanTitle = title.replace(/^Odoo\s*-\s*/i, "").trim();
    if (!title || title === "Odoo") {
        document.title = DEFAULT_TITLE;
    } else if (!cleanTitle.includes(BRAND_NAME)) {
        document.title = `${cleanTitle || "Panel Comercial"} - ${BRAND_NAME}`;
    }
}

applyBranding();
window.addEventListener("hashchange", applyBranding);
window.addEventListener("popstate", applyBranding);
setInterval(applyBranding, 2000);
