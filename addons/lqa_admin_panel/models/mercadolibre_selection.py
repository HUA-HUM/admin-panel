import json

from odoo import fields, models


class LqaMercadolibreSelectionFolder(models.Model):
    _name = "lqa.mercadolibre.selection.folder"
    _description = "Carpeta de seleccion MercadoLibre"
    _order = "write_date desc, id desc"

    name = fields.Char(required=True, string="Nombre")
    description = fields.Text(string="Descripcion")
    line_ids = fields.One2many(
        "lqa.mercadolibre.selection.item",
        "folder_id",
        string="Productos",
    )
    product_count = fields.Integer(
        string="Productos",
        compute="_compute_product_count",
    )
    active = fields.Boolean(default=True)

    def _compute_product_count(self):
        counts = self.env["lqa.mercadolibre.selection.item"].read_group(
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


class LqaMercadolibreSelectionItem(models.Model):
    _name = "lqa.mercadolibre.selection.item"
    _description = "Producto seleccionado MercadoLibre"
    _order = "write_date desc, id desc"

    folder_id = fields.Many2one(
        "lqa.mercadolibre.selection.folder",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_key = fields.Char(required=True, index=True)
    item_id = fields.Char(index=True)
    title = fields.Char()
    thumbnail = fields.Char()
    status = fields.Char()
    brand = fields.Char()
    sku = fields.Char(index=True)
    condition = fields.Char()
    listing_type_id = fields.Char()
    price = fields.Float()
    currency_id = fields.Char()
    available_quantity = fields.Integer()
    revenue = fields.Float()
    orders_count = fields.Integer()
    units_sold = fields.Integer()
    total_visits = fields.Integer()
    order_conversion_rate = fields.Float()
    category_id = fields.Char()
    domain_id = fields.Char()
    permalink = fields.Char()
    date_created = fields.Char()
    last_updated = fields.Char()
    catalog_sold_quantity = fields.Integer()
    avg_ticket = fields.Float()
    first_order_date = fields.Char()
    last_order_date = fields.Char()
    unit_conversion_rate = fields.Float()
    payload_json = fields.Text()

    _sql_constraints = [
        (
            "meli_folder_product_key_unique",
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
            "item_id": self.item_id or "",
            "title": self.title or "",
            "thumbnail": self.thumbnail or "",
            "status": self.status or "",
            "brand": self.brand or "",
            "sku": self.sku or "",
            "condition": self.condition or "",
            "listing_type_id": self.listing_type_id or "",
            "listingTypeId": self.listing_type_id or "",
            "price": self.price,
            "currency_id": self.currency_id or "",
            "available_quantity": self.available_quantity,
            "revenue": self.revenue,
            "orders_count": self.orders_count,
            "units_sold": self.units_sold,
            "total_visits": self.total_visits,
            "order_conversion_rate": self.order_conversion_rate,
            "category_id": self.category_id or "",
            "domain_id": self.domain_id or "",
            "permalink": self.permalink or "",
            "date_created": self.date_created or "",
            "last_updated": self.last_updated or "",
            "catalog_sold_quantity": self.catalog_sold_quantity,
            "avg_ticket": self.avg_ticket,
            "first_order_date": self.first_order_date or "",
            "last_order_date": self.last_order_date or "",
            "unit_conversion_rate": self.unit_conversion_rate,
            "payload": payload,
        }
