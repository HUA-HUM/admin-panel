import json

from odoo import fields, models


class LqaAutomeliSelectionFolder(models.Model):
    _name = "lqa.automeli.selection.folder"
    _description = "Carpeta de seleccion Automeli"
    _order = "write_date desc, id desc"

    name = fields.Char(required=True, string="Nombre")
    description = fields.Text(string="Descripcion")
    line_ids = fields.One2many(
        "lqa.automeli.selection.item",
        "folder_id",
        string="Productos",
    )
    product_count = fields.Integer(
        string="Productos",
        compute="_compute_product_count",
    )
    active = fields.Boolean(default=True)

    def _compute_product_count(self):
        counts = self.env["lqa.automeli.selection.item"].read_group(
            [("folder_id", "in", self.ids)],
            ["folder_id"],
            ["folder_id"],
        )
        count_by_folder = {
            item["folder_id"][0]: item["folder_id_count"]
            for item in counts
            if item.get("folder_id")
        }
        for folder in self:
            folder.product_count = count_by_folder.get(folder.id, 0)


class LqaAutomeliSelectionItem(models.Model):
    _name = "lqa.automeli.selection.item"
    _description = "Producto seleccionado Automeli"
    _order = "write_date desc, id desc"

    folder_id = fields.Many2one(
        "lqa.automeli.selection.folder",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_key = fields.Char(required=True, index=True)
    mla = fields.Char(index=True)
    sku = fields.Char(index=True)
    listing_type_id = fields.Char()
    meli_status = fields.Char()
    amz_status = fields.Char()
    total_price = fields.Float()
    scraped_price = fields.Float()
    meli_sale_price = fields.Float()
    stock_quantity = fields.Integer()
    max_weight = fields.Integer()
    changed = fields.Char()
    sub_status = fields.Char()
    app_status = fields.Char()
    snapshot_created_at = fields.Char()
    snapshot_updated_at = fields.Char()
    payload_json = fields.Text()

    _sql_constraints = [
        (
            "folder_product_key_unique",
            "unique(folder_id, product_key)",
            "El producto ya existe en esta carpeta.",
        ),
    ]

    def to_panel_dict(self):
        self.ensure_one()
        payload = {}
        if self.payload_json:
            try:
                payload = json.loads(self.payload_json)
            except ValueError:
                payload = {}
        return {
            "id": self.id,
            "folderId": self.folder_id.id,
            "productKey": self.product_key,
            "mla": self.mla or "",
            "sku": self.sku or "",
            "listingTypeId": self.listing_type_id or "",
            "meliStatus": self.meli_status or "",
            "amzStatus": self.amz_status or "",
            "totalPrice": self.total_price,
            "scrapedPrice": self.scraped_price,
            "meliSalePrice": self.meli_sale_price,
            "stockQuantity": self.stock_quantity,
            "maxWeight": self.max_weight,
            "changed": self.changed or "",
            "subStatus": self.sub_status or "",
            "appStatus": self.app_status or "",
            "createdAt": self.snapshot_created_at or "",
            "updatedAt": self.snapshot_updated_at or "",
            "payload": payload,
        }
