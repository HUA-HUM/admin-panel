from odoo import fields, models


class LqaAutomeliCatalogItem(models.Model):
    _name = "lqa.automeli.catalog.item"
    _description = "Item de catalogo Automeli"
    _order = "write_date desc, id desc"

    name = fields.Char(string="Producto", required=True)
    sku = fields.Char(string="SKU", index=True)
    external_id = fields.Char(string="ID externo", index=True)
    status = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("ready", "Listo"),
            ("synced", "Sincronizado"),
            ("error", "Error"),
            ("archived", "Archivado"),
        ],
        string="Estado",
        default="draft",
        required=True,
        index=True,
    )
    price = fields.Float(string="Precio")
    stock_qty = fields.Float(string="Stock")
    category = fields.Char(string="Categoria")
    last_sync_at = fields.Datetime(string="Ultima sincronizacion")
    api_payload_preview = fields.Text(string="Vista previa payload")
    notes = fields.Text(string="Notas internas")
    active = fields.Boolean(default=True)
