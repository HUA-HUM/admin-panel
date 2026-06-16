from odoo import fields, models


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
    lqa_api_timeout_seconds = fields.Integer(
        string="Timeout API",
        default=20,
        config_parameter="lqa_admin_panel.api_timeout_seconds",
    )
