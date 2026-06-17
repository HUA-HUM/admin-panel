/** @odoo-module **/

import { registry } from "@web/core/registry";

export const lqaMercadolibrePricingNotificationService = {
    dependencies: ["orm", "notification"],
    start(env, { orm, notification }) {
        async function poll() {
            try {
                const jobs = await orm.call(
                    "lqa.mercadolibre.pricing.service",
                    "get_ready_notifications",
                    []
                );
                if (!jobs.length) {
                    return;
                }
                for (const job of jobs) {
                    notification.add(
                        job.state === "done"
                            ? `Pricing listo: ${job.name}`
                            : `Pricing con error: ${job.name}`,
                        {
                            type: job.state === "done" ? "success" : "danger",
                        }
                    );
                }
                await orm.call(
                    "lqa.mercadolibre.pricing.service",
                    "mark_jobs_notified",
                    [jobs.map((job) => job.id)]
                );
            } catch {
                // The notifier must stay silent if the user has no session or API access.
            }
        }

        window.setTimeout(poll, 8000);
        window.setInterval(poll, 30000);
        return {};
    },
};

registry
    .category("services")
    .add(
        "lqa_mercadolibre_pricing_notifications",
        lqaMercadolibrePricingNotificationService
    );
