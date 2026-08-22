from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class PharmacyExpiryRecord(models.Model):
    _name = "pharmacy.expiry.record"
    _description = "Pharmacy Expiry Record"
    _inherit = ["mail.thread", "mail.activity.mixin", "pharmacy.audit.mixin"]
    _order = "expiry_date, id"

    _pharmacy_audit_fields = (
        "name",
        "product_id",
        "expiry_date",
        "received_quantity",
        "purchase_order_id",
        "stock_picking_id",
        "stock_move_id",
        "active",
    )

    name = fields.Char(
        string="Expiry Reference",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
        domain="[('product_tmpl_id.is_pharmacy_item', '=', True)]",
    )
    product_tmpl_id = fields.Many2one(
        related="product_id.product_tmpl_id",
        store=True,
        index=True,
    )
    internal_reference = fields.Char(related="product_id.default_code", store=True)
    expiry_date = fields.Date(required=True, index=True, tracking=True)
    received_quantity = fields.Float(
        required=True,
        default=0.0,
        digits="Product Unit of Measure",
        tracking=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        required=True,
        ondelete="restrict",
    )
    received_date = fields.Date(default=fields.Date.context_today, index=True)
    vendor_id = fields.Many2one("res.partner", string="Vendor", ondelete="set null", index=True)
    purchase_order_id = fields.Many2one("purchase.order", ondelete="set null", index=True)
    purchase_line_id = fields.Many2one("purchase.order.line", ondelete="set null", index=True)
    stock_picking_id = fields.Many2one("stock.picking", string="Receipt", ondelete="set null", index=True)
    stock_move_id = fields.Many2one("stock.move", ondelete="set null", index=True, copy=False)
    location_id = fields.Many2one("stock.location", string="Received Into", ondelete="set null")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    warning_days = fields.Integer(
        related="product_tmpl_id.pharmacy_expiry_warning_days",
        string="Warning Days",
    )
    days_to_expiry = fields.Integer(compute="_compute_expiry_status", string="Days to Expiry")
    expiry_status = fields.Selection(
        [
            ("expired", "Expired"),
            ("expiring", "Expiring Soon"),
            ("valid", "Valid"),
        ],
        compute="_compute_expiry_status",
        search="_search_expiry_status",
        string="Expiry Status",
    )
    on_hand_qty = fields.Float(
        compute="_compute_on_hand_qty",
        string="On Hand",
        digits="Product Unit of Measure",
    )
    dispensing_line_ids = fields.One2many(
        "pharmacy.dispensing.line",
        "expiry_record_id",
        string="Dispensed Lines",
    )
    dispensed_quantity = fields.Float(
        compute="_compute_dispensed_quantity",
        digits="Product Unit of Measure",
    )
    available_quantity = fields.Float(
        compute="_compute_dispensed_quantity",
        string="Unallocated Receipt Quantity",
        digits="Product Unit of Measure",
        help="Receipt quantity less confirmed dispensing allocated to this expiry record. Native Odoo On Hand remains the stock source of truth.",
    )

    _stock_move_unique = models.Constraint(
        "unique(stock_move_id)",
        "An expiry record already exists for this receipt operation.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("name", _("New")) == _("New"):
                values["name"] = self.env["ir.sequence"].next_by_code(
                    "noels.pharmacy.expiry"
                ) or _("New")
            product = self.env["product.product"].browse(values.get("product_id"))
            values.setdefault("product_uom_id", product.uom_id.id)
        return super().create(vals_list)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id

    @api.depends("expiry_date", "warning_days")
    def _compute_expiry_status(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not record.expiry_date:
                record.days_to_expiry = 0
                record.expiry_status = "valid"
                continue
            record.days_to_expiry = (record.expiry_date - today).days
            if record.expiry_date < today:
                record.expiry_status = "expired"
            elif record.days_to_expiry <= record.warning_days:
                record.expiry_status = "expiring"
            else:
                record.expiry_status = "valid"

    @api.model
    def _search_expiry_status(self, operator, value):
        if operator not in ("=", "!=") or value not in ("expired", "expiring", "valid"):
            return [("id", "=", 0)]
        today = fields.Date.context_today(self)
        records = self.search([("active", "=", True)])
        matching = records.filtered(lambda record: record.expiry_status == value).ids
        return [("id", "in" if operator == "=" else "not in", matching)]

    @api.depends_context("company")
    @api.depends("product_id")
    def _compute_on_hand_qty(self):
        for record in self:
            record.on_hand_qty = record.product_id.with_company(record.company_id).qty_available

    @api.depends(
        "received_quantity",
        "dispensing_line_ids.quantity",
        "dispensing_line_ids.dispensing_id.state",
    )
    def _compute_dispensed_quantity(self):
        for record in self:
            record.dispensed_quantity = sum(
                record.dispensing_line_ids.filtered(
                    lambda line: line.dispensing_id.state == "confirmed"
                ).mapped("quantity")
            )
            record.available_quantity = max(
                record.received_quantity - record.dispensed_quantity,
                0.0,
            )

    @api.constrains("received_quantity")
    def _check_received_quantity(self):
        if any(record.received_quantity < 0 for record in self):
            raise ValidationError(_("Received quantity cannot be negative."))

    def unlink(self):
        if any(record.stock_move_id for record in self):
            raise ValidationError(
                _("Receipt-generated expiry records cannot be deleted. Archive the record to preserve the audit trail.")
            )
        return super().unlink()

    @api.model
    def find_earliest_available(self, product, company=None):
        company = company or self.env.company
        today = fields.Date.context_today(self)
        candidates = self.search(
            [
                ("product_id", "=", product.id),
                ("company_id", "=", company.id),
                ("active", "=", True),
                ("expiry_date", ">=", today),
            ],
            order="expiry_date, id",
        )
        return candidates.filtered(lambda record: record.available_quantity > 0)[:1]


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    pharmacy_expected_expiry_date = fields.Date(
        string="Expected Expiry",
        help="Expected medicine expiry supplied by the vendor. Confirm the actual date on receipt.",
    )


class StockMove(models.Model):
    _inherit = "stock.move"

    pharmacy_expected_expiry_date = fields.Date(
        related="purchase_line_id.pharmacy_expected_expiry_date",
        string="Expected Expiry",
        readonly=True,
    )
    pharmacy_actual_expiry_date = fields.Date(
        string="Actual Expiry",
        copy=False,
        help="Simple Noel's Pharmacy expiry date verified when this medicine is received.",
    )
    pharmacy_expiry_record_id = fields.Many2one(
        "pharmacy.expiry.record",
        string="Expiry Record",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    def write(self, values):
        if "pharmacy_actual_expiry_date" in values and any(
            move.state == "done" for move in self
        ):
            raise ValidationError(
                _("A completed receipt's pharmacy expiry cannot be changed. Archive the incorrect expiry record and create an audited replacement instead.")
            )
        return super().write(values)

    def _action_done(self, cancel_backorder=False):
        incoming = self.filtered(
            lambda move: move.picking_code == "incoming"
            and move.product_id.product_tmpl_id.is_pharmacy_item
            and move.product_id.product_tmpl_id.pharmacy_expiry_tracking
            and float_compare(
                move.quantity,
                0.0,
                precision_rounding=move.product_uom.rounding,
            ) > 0
        )
        today = fields.Date.context_today(self)
        for move in incoming:
            if not move.pharmacy_actual_expiry_date:
                raise ValidationError(
                    _("Enter the actual expiry date for %s before validating this receipt.")
                    % move.product_id.display_name
                )
            if move.pharmacy_actual_expiry_date < today:
                raise ValidationError(
                    _("The received expiry date for %s is already past.")
                    % move.product_id.display_name
                )
        result = super()._action_done(cancel_backorder=cancel_backorder)
        completed = result if getattr(result, "_name", None) == "stock.move" else self
        for move in completed.filtered(
            lambda item: item.id in incoming.ids and not item.pharmacy_expiry_record_id
        ):
            purchase = move.purchase_line_id.order_id
            record = self.env["pharmacy.expiry.record"].create(
                {
                    "product_id": move.product_id.id,
                    "expiry_date": move.pharmacy_actual_expiry_date,
                    "received_quantity": move.quantity,
                    "product_uom_id": move.product_uom.id,
                    "received_date": fields.Date.context_today(move),
                    "vendor_id": purchase.partner_id.id,
                    "purchase_order_id": purchase.id,
                    "purchase_line_id": move.purchase_line_id.id,
                    "stock_picking_id": move.picking_id.id,
                    "stock_move_id": move.id,
                    "location_id": move.location_dest_id.id,
                    "company_id": move.company_id.id,
                }
            )
            move.pharmacy_expiry_record_id = record
        return result
