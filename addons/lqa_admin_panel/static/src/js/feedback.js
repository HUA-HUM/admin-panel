/** @odoo-module **/

// Notificaciones y dialogos de error del panel.
//
// Se envuelve el servicio de notificaciones de Odoo en vez de tocar las ~160
// llamadas a notification.add: cada toast recibe una clase por tipo (para el
// icono y el color) y una duracion acorde a lo que hay que leer.

import { notificationService } from "@web/core/notifications/notification_service";
import { odooExceptionTitleMap } from "@web/core/errors/error_dialogs";

// Un error se lee mas despacio que un "listo". Pasar el mouse por encima
// congela el cierre (Odoo), asi que nadie pierde un mensaje a mitad de lectura.
const AUTOCLOSE_MS = {
    success: 3500,
    info: 5000,
    warning: 6500,
    danger: 9000,
};

const originalStart = notificationService.start;

notificationService.start = function (...args) {
    const service = originalStart.call(this, ...args);
    const originalAdd = service.add;
    return {
        ...service,
        add(message, options = {}) {
            // Odoo usa "warning" cuando no se indica tipo.
            const type = options.type || "warning";
            const delay = options.autocloseDelay ?? AUTOCLOSE_MS[type] ?? 5000;
            const className = [
                "o_lqa_toast",
                `o_lqa_toast--${type}`,
                options.sticky ? "o_lqa_toast--sticky" : "",
                options.title ? "o_lqa_toast--titled" : "",
                options.className || "",
            ]
                .filter(Boolean)
                .join(" ");
            // La barra de tiempo del toast (CSS) dura lo mismo que AUTOCLOSE_MS.
            return originalAdd(message, {
                ...options,
                autocloseDelay: delay,
                className,
            });
        },
    };
};

// Los titulos de los dialogos de error salian en ingles ("Invalid
// Operation", "Validation Error") en un panel que esta todo en castellano.
const TITLES = {
    "odoo.exceptions.UserError": "No se pudo completar",
    "odoo.exceptions.ValidationError": "Revisá los datos",
    "odoo.exceptions.AccessError": "Sin permiso",
    "odoo.exceptions.AccessDenied": "Acceso denegado",
    "odoo.exceptions.MissingError": "El registro ya no existe",
    "odoo.addons.web.controllers.action.MissingActionError": "Pantalla no encontrada",
    "odoo.exceptions.Warning": "Atención",
};

for (const [exceptionName, title] of Object.entries(TITLES)) {
    odooExceptionTitleMap.set(exceptionName, title);
}
