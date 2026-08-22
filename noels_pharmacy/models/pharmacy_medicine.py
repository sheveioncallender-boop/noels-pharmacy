from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_pharmacy_item = fields.Boolean(string="Pharmacy Medicine", index=True)
    pharmacy_generic_name = fields.Char(string="Generic Name", index=True)
    pharmacy_strength = fields.Char(string="Strength")
    pharmacy_dosage_form = fields.Selection(
        [
            ("tablet", "Tablet"),
            ("capsule", "Capsule"),
            ("liquid", "Oral Liquid"),
            ("cream", "Cream"),
            ("ointment", "Ointment"),
            ("drops", "Drops"),
            ("inhaler", "Inhaler"),
            ("injection", "Injection"),
            ("suppository", "Suppository"),
            ("other", "Other"),
        ],
        string="Dosage Form",
    )
    pharmacy_default_route = fields.Selection(
        [
            ("oral", "Oral"),
            ("topical", "Topical"),
            ("inhaled", "Inhaled"),
            ("ophthalmic", "Ophthalmic"),
            ("otic", "Otic"),
            ("nasal", "Nasal"),
            ("rectal", "Rectal"),
            ("vaginal", "Vaginal"),
            ("injection", "Injection"),
            ("other", "Other"),
        ],
        string="Default Route",
    )
    pharmacy_registration_number = fields.Char(string="Drug Registration Number", index=True)
    pharmacy_manufacturer = fields.Char(string="Manufacturer")
    pharmacy_storage_instructions = fields.Char(string="Storage Instructions")
    pharmacy_default_directions = fields.Text(string="Default Dispensing Directions")
    pharmacy_default_caution = fields.Text(string="Default Caution")
    pharmacy_rx_required = fields.Boolean(string="Prescription Required")
    pharmacy_approval_required = fields.Boolean(string="Pharmacist Approval Required")
    pharmacy_substitution_allowed = fields.Boolean(string="Generic Substitution Allowed", default=True)
    pharmacy_active_ingredient_ids = fields.Many2many(
        "pharmacy.active.ingredient",
        "pharmacy_product_ingredient_rel",
        "product_tmpl_id",
        "ingredient_id",
        string="Active Ingredients",
    )
    pharmacy_therapeutic_class_id = fields.Many2one(
        "pharmacy.therapeutic.class",
        string="Therapeutic Class",
        index=True,
    )
    pharmacy_register_type_ids = fields.Many2many(
        "pharmacy.register.type",
        "pharmacy_product_register_rel",
        "product_tmpl_id",
        "register_type_id",
        string="Regulatory Registers",
    )
    pharmacy_expiry_tracking = fields.Boolean(
        string="Track Pharmacy Expiry",
        default=True,
        help="Require a simple receipt-level expiry date without requiring Odoo lot tracking.",
    )
    pharmacy_expiry_warning_days = fields.Integer(
        string="Expiry Warning Days",
        default=30,
        help="Show this medicine as expiring soon this many days before expiry.",
    )
    pharmacy_low_stock_threshold = fields.Float(
        string="Low Stock Threshold",
        default=0.0,
        digits="Product Unit of Measure",
        help="Show this medicine in Low Stock Monitoring when On Hand or Forecasted reaches this quantity.",
    )
    pharmacy_expiry_record_ids = fields.One2many(
        "pharmacy.expiry.record",
        "product_tmpl_id",
        string="Expiry Records",
    )
    pharmacy_expiry_count = fields.Integer(compute="_compute_pharmacy_expiry_summary")
    pharmacy_expiring_count = fields.Integer(compute="_compute_pharmacy_expiry_summary")
    pharmacy_earliest_expiry_date = fields.Date(
        compute="_compute_pharmacy_expiry_summary",
        string="Earliest Expiry",
    )
    pharmacy_low_stock_status = fields.Selection(
        [
            ("negative", "Negative Stock"),
            ("out", "Out of Stock"),
            ("low", "Low Stock"),
            ("in_stock", "In Stock"),
        ],
        compute="_compute_pharmacy_low_stock_status",
        search="_search_pharmacy_low_stock_status",
        string="Stock Status",
    )

    @api.onchange("pharmacy_register_type_ids")
    def _onchange_pharmacy_register_types(self):
        if self.pharmacy_register_type_ids:
            self.is_pharmacy_item = True
            self.pharmacy_rx_required = True
            self.pharmacy_approval_required = True

    @api.onchange("is_pharmacy_item")
    def _onchange_is_pharmacy_item(self):
        if self.is_pharmacy_item:
            self.pharmacy_expiry_tracking = True

    @api.depends(
        "pharmacy_expiry_record_ids.expiry_date",
        "pharmacy_expiry_record_ids.active",
    )
    def _compute_pharmacy_expiry_summary(self):
        today = fields.Date.context_today(self)
        for template in self:
            records = template.pharmacy_expiry_record_ids.filtered(
                lambda record: record.active and record.expiry_date >= today
            )
            template.pharmacy_expiry_count = len(template.pharmacy_expiry_record_ids.filtered("active"))
            template.pharmacy_expiring_count = len(
                records.filtered(
                    lambda record: record.days_to_expiry <= template.pharmacy_expiry_warning_days
                )
            )
            template.pharmacy_earliest_expiry_date = min(records.mapped("expiry_date"), default=False)

    @api.depends_context("company")
    @api.depends("qty_available", "virtual_available", "pharmacy_low_stock_threshold")
    def _compute_pharmacy_low_stock_status(self):
        for template in self:
            if template.qty_available < 0:
                template.pharmacy_low_stock_status = "negative"
            elif template.qty_available == 0:
                template.pharmacy_low_stock_status = "out"
            elif (
                template.qty_available <= template.pharmacy_low_stock_threshold
                or template.virtual_available <= template.pharmacy_low_stock_threshold
            ):
                template.pharmacy_low_stock_status = "low"
            else:
                template.pharmacy_low_stock_status = "in_stock"

    @api.model
    def _search_pharmacy_low_stock_status(self, operator, value):
        values = value if isinstance(value, (list, tuple, set)) else [value]
        products = self.search([("is_pharmacy_item", "=", True)])
        matching = products.filtered(lambda template: template.pharmacy_low_stock_status in values).ids
        positive = operator in ("=", "in")
        return [("id", "in" if positive else "not in", matching)]

    @api.constrains("pharmacy_expiry_warning_days", "pharmacy_low_stock_threshold")
    def _check_monitoring_values(self):
        for template in self:
            if template.pharmacy_expiry_warning_days < 0:
                raise ValidationError(_("Expiry warning days cannot be negative."))
            if template.pharmacy_low_stock_threshold < 0:
                raise ValidationError(_("Low stock threshold cannot be negative."))

    def action_view_pharmacy_expiry_records(self):
        self.ensure_one()
        action = self.env.ref("noels_pharmacy.action_pharmacy_expiry_monitoring").read()[0]
        action["domain"] = [("product_tmpl_id", "=", self.id)]
        action["context"] = {
            "default_product_id": self.product_variant_id.id,
            "default_company_id": self.env.company.id,
        }
        return action

    def action_view_pharmacy_expiring_records(self):
        self.ensure_one()
        action = self.action_view_pharmacy_expiry_records()
        today = fields.Date.context_today(self)
        warning_date = fields.Date.add(today, days=self.pharmacy_expiry_warning_days)
        action["domain"] += [
            ("expiry_date", ">=", today),
            ("expiry_date", "<=", warning_date),
            ("active", "=", True),
        ]
        return action

    def action_view_pharmacy_dispensing_history(self):
        self.ensure_one()
        action = self.env.ref("noels_pharmacy.action_pharmacy_dispensing_log").read()[0]
        action["domain"] = [("product_id.product_tmpl_id", "=", self.id)]
        return action
