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
