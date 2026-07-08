from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    lqa_api_environment = fields.Selection(
        selection=[
            ("development", "Desarrollo"),
            ("staging", "Staging"),
            ("production", "Produccion"),
        ],
        string="Entorno API",
        default="development",
        config_parameter="lqa_admin_panel.api_environment",
    )
    lqa_api_base_url = fields.Char(
        string="URL base API",
        config_parameter="lqa_admin_panel.api_base_url",
    )
    lqa_api_token = fields.Char(
        string="Token interno",
        config_parameter="lqa_admin_panel.api_token",
    )
    lqa_mercadolibre_api_path = fields.Char(
        string="Ruta MercadoLibre",
        default="/mercadolibre",
        config_parameter="lqa_admin_panel.mercadolibre_api_path",
    )
    lqa_mercadolibre_catalog_url = fields.Char(
        string="URL catalogo MercadoLibre",
        default=(
            "https://catalog-meli.loquieroaca.com/"
            "analytics/products/performance"
        ),
        config_parameter="lqa_admin_panel.mercadolibre_catalog_url",
    )
    lqa_mercadolibre_delete_url = fields.Char(
        string="URL eliminador MercadoLibre",
        default=(
            "https://api.meli.loquieroaca.com/"
            "meli/products/bulk/delete"
        ),
        config_parameter="lqa_admin_panel.mercadolibre_delete_url",
    )
    lqa_mercadolibre_delete_api_key = fields.Char(
        string="Clave interna eliminador",
        config_parameter="lqa_admin_panel.mercadolibre_delete_api_key",
    )
    lqa_mercadolibre_pricing_url = fields.Char(
        string="URL Pricing MercadoLibre",
        default=(
            "https://api.price.loquieroaca.com/"
            "internal/getProfit/details/bulk"
        ),
        config_parameter="lqa_admin_panel.mercadolibre_pricing_url",
    )
    lqa_mercadolibre_pricing_api_key = fields.Char(
        string="API key Pricing MercadoLibre",
        config_parameter="lqa_admin_panel.mercadolibre_pricing_api_key",
    )
    lqa_mercadolibre_pricing_timeout_seconds = fields.Integer(
        string="Timeout Pricing MercadoLibre",
        default=300,
        config_parameter="lqa_admin_panel.mercadolibre_pricing_timeout_seconds",
    )
    lqa_mercadolibre_promotions_stats_url = fields.Char(
        string="URL stats promociones",
        default="http://cpe.loquieroaca.com/promotions/stats",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_stats_url",
    )
    lqa_mercadolibre_promotions_url = fields.Char(
        string="URL promociones",
        default="http://cpe.loquieroaca.com/promotions",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_url",
    )
    lqa_mercadolibre_promotions_catalogs_url = fields.Char(
        string="URL catalogo promociones",
        default="http://cpe.loquieroaca.com/promotions/catalogs",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_catalogs_url",
    )
    lqa_mercadolibre_aporte_orders_url = fields.Char(
        string="URL ordenes aporte ML",
        default=(
            "https://api.madre.loquieroaca.com/"
            "api/mercadolibre/orders/aporte-ml"
        ),
        config_parameter="lqa_admin_panel.mercadolibre_aporte_orders_url",
    )
    lqa_mercadolibre_aporte_analytics_url = fields.Char(
        string="URL analytics aporte ML",
        default=(
            "https://api.madre.loquieroaca.com/"
            "api/mercadolibre/orders/analytics/aporte-ml/timeseries"
        ),
        config_parameter="lqa_admin_panel.mercadolibre_aporte_analytics_url",
    )
    lqa_mercadolibre_promotions_timeout_seconds = fields.Integer(
        string="Timeout promociones",
        default=120,
        config_parameter="lqa_admin_panel.mercadolibre_promotions_timeout_seconds",
    )
    lqa_mercadolibre_promotions_action_timeout_seconds = fields.Integer(
        string="Timeout acciones promociones",
        default=300,
        config_parameter="lqa_admin_panel.mercadolibre_promotions_action_timeout_seconds",
    )
    lqa_mercadolibre_promotions_sync_url = fields.Char(
        string="URL sync promociones",
        default="http://cpe.loquieroaca.com/promotions/sync",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_sync_url",
    )
    lqa_mercadolibre_promotions_activate_url = fields.Char(
        string="URL activar promociones",
        default="http://cpe.loquieroaca.com/promotions/activate",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_activate_url",
    )
    lqa_mercadolibre_promotions_deactivate_url = fields.Char(
        string="URL desactivar promociones",
        default="http://cpe.loquieroaca.com/promotions/deactivate",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_deactivate_url",
    )
    lqa_mercadolibre_promotions_deactivate_failed_url = fields.Char(
        string="URL reintentar desactivaciones",
        default="http://cpe.loquieroaca.com/promotions/deactivate-failed",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_deactivate_failed_url",
    )
    lqa_mercadolibre_promotions_sync_one_url = fields.Char(
        string="URL sync una promocion",
        default="http://cpe.loquieroaca.com/promotions/sync-one",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_sync_one_url",
    )
    lqa_mercadolibre_promotions_datadog_base_url = fields.Char(
        string="URL base Datadog",
        default="https://us5.datadoghq.com/logs/livetail",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_datadog_base_url",
    )
    lqa_mercadolibre_promotions_datadog_service = fields.Char(
        string="Servicio Datadog",
        default="central-promos-enginee",
        config_parameter="lqa_admin_panel.mercadolibre_promotions_datadog_service",
    )
    lqa_automeli_api_path = fields.Char(
        string="Ruta Automeli",
        default="/automeli",
        config_parameter="lqa_admin_panel.automeli_api_path",
    )
    lqa_automeli_catalog_url = fields.Char(
        string="URL catalogo Automeli",
        default=(
            "https://api.madre.loquieroaca.com/"
            "api/automeli/product-snapshots/all"
        ),
        config_parameter="lqa_admin_panel.automeli_catalog_url",
    )
    lqa_automeli_catalog_status_url = fields.Char(
        string="URL estado catalogo Automeli",
        default=(
            "https://api.madre.loquieroaca.com/"
            "api/automeli/product-snapshots/last-updated"
        ),
        config_parameter="lqa_admin_panel.automeli_catalog_status_url",
    )
    lqa_retailers_madre_api_url = fields.Char(
        string="URL Madre Retailers",
        default="https://api.madre.loquieroaca.com",
        config_parameter="lqa_admin_panel.retailers_madre_api_url",
    )
    lqa_retailers_products_api_url = fields.Char(
        string="URL Products Retailers",
        default="https://api.products.loquieroaca.com",
        config_parameter="lqa_admin_panel.retailers_products_api_url",
    )
    lqa_retailers_madre_api_token = fields.Char(
        string="Token Madre Retailers",
        config_parameter="lqa_admin_panel.retailers_madre_api_token",
    )
    lqa_retailers_pricing_url = fields.Char(
        string="URL Pricing Retailers",
        default=(
            "https://api.price.loquieroaca.com/"
            "internal/getProfit/channel/details/bulk"
        ),
        config_parameter="lqa_admin_panel.retailers_pricing_url",
    )
    lqa_retailers_pricing_api_key = fields.Char(
        string="API key Pricing Retailers",
        config_parameter="lqa_admin_panel.retailers_pricing_api_key",
    )
    lqa_retailers_pricing_timeout_seconds = fields.Integer(
        string="Timeout Pricing Retailers",
        default=300,
        config_parameter="lqa_admin_panel.retailers_pricing_timeout_seconds",
    )
    lqa_retailers_orders_proxy_url = fields.Char(
        string="URL Orders Retailers",
        default="https://order.api.loquieroaca.com/orders",
        config_parameter="lqa_admin_panel.retailers_orders_proxy_url",
    )
    lqa_retailers_marketplace_api_url = fields.Char(
        string="URL Marketplace Retailers",
        default="https://api.marketplace.loquieroaca.com",
        config_parameter="lqa_admin_panel.retailers_marketplace_api_url",
    )
    lqa_retailers_orders_api_token = fields.Char(
        string="Token Orders Retailers",
        config_parameter="lqa_admin_panel.retailers_orders_api_token",
    )
    lqa_retailers_timeout_seconds = fields.Integer(
        string="Timeout Retailers",
        default=60,
        config_parameter="lqa_admin_panel.retailers_timeout_seconds",
    )
    lqa_retailers_orders_timeout_seconds = fields.Integer(
        string="Timeout Orders Retailers",
        default=90,
        config_parameter="lqa_admin_panel.retailers_orders_timeout_seconds",
    )
    lqa_retailers_teams_notifications_enabled = fields.Boolean(
        string="Activar notificaciones Teams",
        config_parameter="lqa_admin_panel.retailers_teams_notifications_enabled",
    )
    lqa_retailers_teams_webhook_url = fields.Char(
        string="Webhook Microsoft Teams",
        config_parameter="lqa_admin_panel.retailers_teams_webhook_url",
    )
    lqa_retailers_teams_orders_mode = fields.Selection(
        selection=[
            ("last24", "Ultimas 24h"),
            ("recent24", "Recent 24h"),
            ("recent48", "Recent 48h"),
            ("recent72", "Recent 72h"),
        ],
        string="Periodo Teams",
        default="last24",
        config_parameter="lqa_admin_panel.retailers_teams_orders_mode",
    )
    lqa_retailers_teams_order_statuses = fields.Char(
        string="Estados a notificar",
        default="",
        config_parameter="lqa_admin_panel.retailers_teams_order_statuses",
    )
    lqa_retailers_teams_max_orders_per_message = fields.Integer(
        string="Max ordenes por mensaje",
        default=20,
        config_parameter="lqa_admin_panel.retailers_teams_max_orders_per_message",
    )
    lqa_retailers_teams_timeout_seconds = fields.Integer(
        string="Timeout Teams",
        default=20,
        config_parameter="lqa_admin_panel.retailers_teams_timeout_seconds",
    )
    lqa_retailers_teams_retention_days = fields.Integer(
        string="Retencion log Teams",
        default=45,
        config_parameter="lqa_admin_panel.retailers_teams_retention_days",
    )
    lqa_accounting_invoice_api_url = fields.Char(
        string="URL Invoice ARCA",
        default="https://invoice.loquieroaca.com",
        config_parameter="lqa_admin_panel.accounting_invoice_api_url",
    )
    lqa_accounting_invoice_api_key = fields.Char(
        string="Clave interna Invoice ARCA",
        config_parameter="lqa_admin_panel.accounting_invoice_api_key",
    )
    lqa_accounting_madre_api_url = fields.Char(
        string="URL Madre Contable",
        default="https://api.madre.loquieroaca.com",
        config_parameter="lqa_admin_panel.accounting_madre_api_url",
    )
    lqa_accounting_madre_api_key = fields.Char(
        string="Clave interna Madre Contable",
        config_parameter="lqa_admin_panel.accounting_madre_api_key",
    )
    lqa_accounting_timeout_seconds = fields.Integer(
        string="Timeout Contable",
        default=120,
        config_parameter="lqa_admin_panel.accounting_timeout_seconds",
    )
    lqa_api_timeout_seconds = fields.Integer(
        string="Timeout API",
        default=20,
        config_parameter="lqa_admin_panel.api_timeout_seconds",
    )

    def action_lqa_test_teams_notification(self):
        self.ensure_one()
        self.env["lqa.retailers.teams.notification"].sudo().send_test_notification()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Microsoft Teams"),
                "message": _("Mensaje de prueba enviado a Teams."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_lqa_send_teams_orders_now(self):
        self.ensure_one()
        result = (
            self.env["lqa.retailers.teams.notification"]
            .sudo()
            ._cron_notify_new_orders()
        )
        count = result.get("count", 0) if isinstance(result, dict) else 0
        sent = bool(result.get("sent")) if isinstance(result, dict) else False
        message = (
            _("Se enviaron %s ordenes nuevas a Teams.") % count
            if sent
            else _("No habia ordenes nuevas para notificar.")
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Microsoft Teams"),
                "message": message,
                "type": "success" if sent else "info",
                "sticky": False,
            },
        }
