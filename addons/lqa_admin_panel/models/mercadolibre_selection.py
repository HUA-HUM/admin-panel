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
        string="Cantidad de productos",
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


class LqaMercadolibreSelectionJob(models.Model):
    _name = "lqa.mercadolibre.selection.job"
    _description = "Guardado masivo de seleccion MercadoLibre"
    _order = "create_date desc, id desc"

    folder_id = fields.Many2one(
        "lqa.mercadolibre.selection.folder",
        required=True,
        ondelete="cascade",
        index=True,
    )
    requested_by_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("queued", "En cola"),
            ("running", "Procesando"),
            ("done", "Completado"),
            ("failed", "Fallido"),
            ("cancelled", "Cancelado"),
        ],
        required=True,
        default="queued",
        index=True,
        readonly=True,
    )
    worker_token = fields.Char(
        readonly=True,
        index=True,
        help="Identifica al worker que tiene tomado el job. Evita que dos "
        "procesos avancen la misma carpeta en paralelo.",
    )
    source_type = fields.Selection(
        [("filter", "Filtro"), ("mla_file", "Archivo de MLAs")],
        default="filter",
        required=True,
        readonly=True,
        index=True,
    )
    input_filename = fields.Char(readonly=True)
    mla_codes_json = fields.Text(readonly=True)
    filters_json = fields.Text(required=True, readonly=True)
    initial_folder_count = fields.Integer(readonly=True)
    initial_count_recorded = fields.Boolean(default=False, readonly=True)
    matched_count = fields.Integer(readonly=True)
    processed_count = fields.Integer(readonly=True)
    cursor_offset = fields.Integer(readonly=True)
    enrich_offset = fields.Integer(
        readonly=True,
        help="MLAs ya enriquecidos contra Catalog API. Avanza despues de "
        "cursor_offset, que solo cuenta los MLAs guardados en la carpeta.",
    )
    added_count = fields.Integer(readonly=True)
    updated_count = fields.Integer(readonly=True)
    not_found_count = fields.Integer(readonly=True)
    invalid_count = fields.Integer(readonly=True)
    retry_count = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)
    started_at = fields.Datetime(readonly=True)
    last_progress_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)

    def _cron_process_pending_jobs(self):
        return self.env[
            "lqa.mercadolibre.catalog.service"
        ].process_pending_selection_jobs()


class LqaMercadolibreCatalogQuery(models.Model):
    _name = "lqa.mercadolibre.catalog.query"
    _description = "Consulta asincronica del catalogo MercadoLibre"
    _order = "create_date desc, id desc"

    requested_by_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("queued", "En cola"),
            ("running", "Consultando"),
            ("done", "Completada"),
            ("failed", "Fallida"),
        ],
        required=True,
        default="queued",
        readonly=True,
        index=True,
    )
    filters_json = fields.Text(required=True, readonly=True)
    result_json = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)


class LqaMercadolibreCatalogExport(models.Model):
    _name = "lqa.mercadolibre.catalog.export"
    _description = "Exportacion a Excel del catalogo MercadoLibre"
    _order = "create_date desc, id desc"

    requested_by_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("queued", "En cola"),
            ("running", "Exportando"),
            ("done", "Listo"),
            ("failed", "Fallido"),
            ("cancelled", "Cancelado"),
        ],
        required=True,
        default="queued",
        index=True,
        readonly=True,
    )
    worker_token = fields.Char(readonly=True, index=True)
    filters_json = fields.Text(required=True, readonly=True)
    columns_json = fields.Text(required=True, readonly=True)
    part_count = fields.Integer(required=True, default=1, readonly=True)
    matched_count = fields.Integer(readonly=True)
    processed_count = fields.Integer(readonly=True)
    cursor_offset = fields.Integer(readonly=True)
    rows_per_part = fields.Integer(readonly=True)
    staging_dir = fields.Char(readonly=True)
    export_path = fields.Char(readonly=True)
    export_size = fields.Integer(readonly=True)
    retry_count = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)
    started_at = fields.Datetime(readonly=True)
    last_progress_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)

    def _cron_process_pending_exports(self):
        return self.env[
            "lqa.mercadolibre.catalog.service"
        ].process_pending_catalog_exports()


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
