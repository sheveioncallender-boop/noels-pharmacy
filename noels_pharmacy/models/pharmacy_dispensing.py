import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


class PharmacyDispensing(models.Model):
    _name = "pharmacy.dispensing"
    _description = "Pharmacy Dispensing"
    _inherit = ["mail.thread", "mail.activity.mixin", "pharmacy.audit.mixin"]
    _order = "dispensed_at desc, id desc"

    _pharmacy_audit_fields = (
        "name",
        "prescription_id",
        "pharmacist_id",
        "dispensed_at",
        "source_type",
        "source_reference",
        "checkout_barcode",
        "checkout_order_uuid",
        "prepared_at",
        "label_size",
        "label_print_count",
        "state",
        "reversal_reason",
    )

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"), index=True)
    prescription_id = fields.Many2one(
        "pharmacy.prescription",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    patient_id = fields.Many2one(related="prescription_id.patient_id", store=True, index=True)
    prescriber_id = fields.Many2one(related="prescription_id.prescriber_id", store=True, index=True)
    pharmacist_id = fields.Many2one(
        "pharmacy.staff.profile",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    pharmacist_initials = fields.Char(related="pharmacist_id.initials", store=True)
    prepared_at = fields.Datetime(readonly=True, copy=False, tracking=True)
    dispensed_at = fields.Datetime(readonly=True, copy=False, tracking=True)
    source_type = fields.Selection(
        [
            ("manual", "Pharmacy Backend"),
            ("sale", "Sales"),
            ("pos", "Point of Sale"),
            ("website", "Website"),
        ],
        required=True,
        default="manual",
        tracking=True,
    )
    source_reference = fields.Char(index=True, tracking=True)
    checkout_barcode = fields.Char(
        string="POS Checkout Barcode",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
        help="Secure fill-level barcode scanned at POS to load this prepared prescription.",
    )
    checkout_order_uuid = fields.Char(
        string="POS Checkout Order UUID",
        readonly=True,
        copy=False,
        index=True,
    )
    label_size = fields.Selection(
        [
            ("3x2", "3 × 2 inch (76.2 × 50.8 mm)"),
            ("4x2", "4 × 2 inch (101.6 × 50.8 mm)"),
        ],
        string="Medication Label Size",
        required=True,
        default="3x2",
        tracking=True,
        help="Default paper size used when medication labels are printed for this fill.",
    )
    label_print_count = fields.Integer(readonly=True, copy=False, default=0)
    last_label_printed_at = fields.Datetime(readonly=True, copy=False)
    last_label_printed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    line_ids = fields.One2many("pharmacy.dispensing.line", "dispensing_id", copy=True)
    state = fields.Selection(
        [
            ("draft", "Draft / Preparing"),
            ("ready", "Ready for POS"),
            ("confirmed", "Paid / Dispensed"),
            ("reversed", "Reversed"),
        ],
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )
    reversal_reason = fields.Text(copy=False, tracking=True)
    reversed_at = fields.Datetime(readonly=True, copy=False)
    reversed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    company_id = fields.Many2one(related="prescription_id.company_id", store=True, index=True)

    _checkout_barcode_unique = models.Constraint(
        "unique(checkout_barcode)",
        "A pharmacy checkout barcode must be unique.",
    )
    _checkout_order_uuid_unique = models.Constraint(
        "unique(checkout_order_uuid)",
        "A POS cart can only contain one prepared prescription.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("name", _("New")) == _("New"):
                values["name"] = self.env["ir.sequence"].next_by_code("noels.pharmacy.dispensing") or _("New")
            if values.get("prescription_id") and not values.get("pharmacist_id"):
                prescription = self.env["pharmacy.prescription"].browse(values["prescription_id"])
                staff = prescription._current_staff_profile()
                if staff:
                    values["pharmacist_id"] = staff.id
        return super().create(vals_list)

    @api.onchange("prescription_id")
    def _onchange_prescription_id(self):
        if not self.prescription_id:
            return
        staff = self.prescription_id._current_staff_profile()
        if staff:
            self.pharmacist_id = staff
        existing = {line.prescription_line_id.id for line in self.line_ids}
        commands = []
        lines_to_prepare = self.prescription_id.line_ids.filtered(
            lambda item: item.remaining_qty > 0
            and (
                not self.prescription_id.partial_fill_open
                or item.partial_fill_qty > 0
            )
            and item.quantity_to_supply > 0
        )
        for line in lines_to_prepare:
            if line.id in existing:
                continue
            commands.append(
                (
                    0,
                    0,
                    {
                        "prescription_line_id": line.id,
                        "product_id": (line.substituted_product_id or line.product_id).id,
                        "quantity": min(
                            line.quantity_to_supply,
                            line.partial_fill_qty or line.remaining_qty,
                        ),
                        "product_uom_id": line.product_uom_id.id,
                        "dispensing_instructions": line.dispensing_instructions,
                        "expiry_record_id": self.env[
                            "pharmacy.expiry.record"
                        ].find_earliest_available(
                            line.substituted_product_id or line.product_id,
                            self.prescription_id.company_id,
                        ).id,
                    },
                )
            )
        self.line_ids = commands

    @api.model
    def _new_checkout_barcode(self):
        """Generate a scanner-friendly value without exposing patient information."""
        # Fifteen Code 128 characters remain crisp on the selected 3 x 2 inch
        # direct-thermal labels while retaining 48 random bits.
        return "NPX%s" % uuid.uuid4().hex[:12].upper()

    def _validate_prepared_lines(self):
        for dispensing in self:
            if dispensing.prescription_id.state not in ("approved", "partially_dispensed"):
                raise UserError(_("The prescription must be pharmacist-approved before preparation."))
            if dispensing.pharmacist_id.role not in ("pharmacist", "manager"):
                raise UserError(_("The responsible staff profile must be a pharmacist or pharmacy manager."))
            if not dispensing.line_ids:
                raise UserError(_("Add at least one medicine to the prepared fill."))
            for line in dispensing.line_ids:
                if line.quantity <= 0:
                    raise UserError(_("Every prepared quantity must be greater than zero."))
                if float_compare(
                    line.quantity,
                    line.prescription_line_id.remaining_qty,
                    precision_rounding=line.product_uom_id.rounding,
                ) > 0:
                    raise UserError(
                        _("The prepared quantity for %s exceeds the remaining authorised balance.")
                        % line.product_id.display_name
                    )
                if line.product_id.product_tmpl_id.pharmacy_expiry_tracking:
                    if not line.expiry_record_id:
                        raise UserError(
                            _("No usable pharmacy expiry record is available for %s. Receive stock with an expiry date or add an expiry record.")
                            % line.product_id.display_name
                        )
                    if line.expiry_date < fields.Date.context_today(line):
                        raise UserError(
                            _("The selected pharmacy expiry record for %s has expired.")
                            % line.product_id.display_name
                        )

    def action_ready_for_pos(self):
        """Lock the prepared fill, assign its barcode, and print medication labels."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only a draft preparation can be marked ready for POS."))
        self._validate_prepared_lines()
        self.prescription_id._assign_permanent_number()
        for line in self.line_ids:
            line.with_context(
                skip_pharmacy_audit=True,
                allow_pharmacy_balance_snapshot=True,
            ).write(
                {
                    "remaining_after": max(
                        line.prescription_line_id.remaining_qty - line.quantity,
                        0.0,
                    )
                }
            )
        self.write(
            {
                "state": "ready",
                "source_type": "pos",
                "prepared_at": fields.Datetime.now(),
                "checkout_barcode": self._new_checkout_barcode(),
                "checkout_order_uuid": False,
            }
        )
        return self._label_report_action()

    def action_return_to_preparation(self):
        for dispensing in self:
            if dispensing.state != "ready" or dispensing.pos_order_id:
                raise UserError(_("Only an unpaid POS preparation can return to Draft."))
            dispensing.write(
                {
                    "state": "draft",
                    "prepared_at": False,
                    "checkout_barcode": False,
                    "checkout_order_uuid": False,
                }
            )
            dispensing.line_ids.with_context(
                skip_pharmacy_audit=True,
                allow_pharmacy_balance_snapshot=True,
            ).write({"remaining_after": 0.0})
        return True

    def action_print_labels(self):
        return self._label_report_action()

    def action_print_labels_3x2(self):
        return self._label_report_action("3x2")

    def action_print_labels_4x2(self):
        return self._label_report_action("4x2")

    def _label_report_xmlid(self, label_size=None):
        self.ensure_one()
        size = label_size or self.label_size
        if size == "4x2":
            return "noels_pharmacy.action_report_pharmacy_label_4x2"
        return "noels_pharmacy.action_report_pharmacy_label"

    def _label_report_action(self, label_size=None):
        self.ensure_one()
        if self.state not in ("ready", "confirmed"):
            raise UserError(_("Prepare or confirm this fill before printing its labels."))
        size = label_size or self.label_size
        self._log_label_print(size)
        return self.env.ref(self._label_report_xmlid(size)).report_action(self.line_ids)

    def _log_label_print(self, label_size=None):
        printed_at = fields.Datetime.now()
        for dispensing in self:
            size = label_size or dispensing.label_size
            size_label = dict(dispensing._fields["label_size"].selection).get(size, size)
            dispensing.with_context(skip_pharmacy_audit=True).write(
                {
                    "label_print_count": dispensing.label_print_count + 1,
                    "last_label_printed_at": printed_at,
                    "last_label_printed_by_id": self.env.user.id,
                }
            )
            dispensing.message_post(
                body=_("Medication labels (%s) printed by %s.")
                % (size_label, self.env.user.display_name),
                subtype_xmlid="mail.mt_note",
            )

    @api.model
    def _check_pos_checkout_access(self):
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Only an authorised Point of Sale user can scan prescription barcodes."))

    @api.model
    def pos_load_prepared_checkout(self, barcode, order_uuid):
        """Return a ready fill to POS and associate it with the current unsaved cart."""
        self._check_pos_checkout_access()
        barcode = (barcode or "").strip().upper()
        order_uuid = (order_uuid or "").strip()
        if not barcode or not order_uuid:
            return {"ok": False, "message": _("The prescription barcode or POS cart identifier is missing.")}
        dispensing = self.sudo().search(
            [
                ("checkout_barcode", "=", barcode),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        if not dispensing:
            return {"ok": False, "message": _("This is not a valid Noel's Pharmacy checkout barcode.")}
        if dispensing.state == "confirmed":
            return {"ok": False, "message": _("This prescription fill has already been paid and dispensed.")}
        if dispensing.state != "ready":
            return {"ok": False, "message": _("This prescription fill is not ready for POS checkout.")}
        prescription = dispensing.prescription_id
        if prescription.state not in ("approved", "partially_dispensed"):
            return {"ok": False, "message": _("This prescription is no longer approved for checkout.")}
        if prescription.valid_until and prescription.valid_until < fields.Date.context_today(self):
            return {"ok": False, "message": _("This prescription has expired and must be reviewed by the pharmacist.")}
        unavailable = dispensing.line_ids.filtered(
            lambda line: not line.product_id.product_tmpl_id.available_in_pos
        )
        if unavailable:
            return {
                "ok": False,
                "message": _("These prepared medicines are not enabled for POS: %s")
                % ", ".join(unavailable.mapped("product_id.display_name")),
            }
        other = self.sudo().search(
            [
                ("checkout_order_uuid", "=", order_uuid),
                ("id", "!=", dispensing.id),
                ("state", "=", "ready"),
            ],
            limit=1,
        )
        if other:
            return {"ok": False, "message": _("This POS cart already contains another prepared prescription.")}
        # The most recent scan owns the unpaid preparation. This permits recovery
        # when a POS cart was abandoned without creating a duplicate dispensing.
        dispensing.write({"checkout_order_uuid": order_uuid})
        return {
            "ok": True,
            "exists": True,
            "dispensing_id": dispensing.id,
            "prescription_id": prescription.id,
            "reference": prescription.name,
            "fill_reference": dispensing.name,
            "barcode": dispensing.checkout_barcode,
            "patient_name": prescription.patient_id.name,
            "purchaser_partner_id": prescription.purchaser_partner_id.id,
            "lines": [
                {
                    "product_id": line.product_id.id,
                    "name": line.product_id.display_name,
                    "quantity": line.quantity,
                    "instructions": line.dispensing_instructions,
                }
                for line in dispensing.line_ids
            ],
        }

    @api.model
    def pos_validate_checkout(self, order_uuid, lines):
        self._check_pos_checkout_access()
        dispensing = self.sudo().search(
            [
                ("checkout_order_uuid", "=", (order_uuid or "").strip()),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        if not dispensing:
            return {"ok": True, "prepared": False}
        if dispensing.state != "ready":
            return {"ok": False, "message": _("The prepared prescription is no longer available for payment.")}
        requested = {}
        for item in lines or []:
            product_id = int(item.get("product_id") or 0)
            requested[product_id] = requested.get(product_id, 0.0) + float(item.get("quantity") or 0.0)
        prepared = {}
        for line in dispensing.line_ids:
            prepared[line.product_id.id] = prepared.get(line.product_id.id, 0.0) + line.quantity
        for product_id, prepared_qty in prepared.items():
            product = self.env["product.product"].sudo().browse(product_id)
            cart_qty = requested.get(product_id, 0.0)
            if float_compare(cart_qty, prepared_qty, precision_rounding=product.uom_id.rounding) < 0:
                return {
                    "ok": False,
                    "message": _("The POS quantity for %s is below the pharmacist-prepared quantity.")
                    % product.display_name,
                }
            if (
                product.product_tmpl_id.pharmacy_rx_required
                or product.product_tmpl_id.pharmacy_approval_required
            ) and float_compare(
                cart_qty,
                prepared_qty,
                precision_rounding=product.uom_id.rounding,
            ) != 0:
                return {
                    "ok": False,
                    "message": _("The regulated quantity for %s must match the prepared prescription exactly.")
                    % product.display_name,
                }
        return {"ok": True, "prepared": True, "dispensing_id": dispensing.id}

    def action_confirm(self):
        for dispensing in self:
            if dispensing.state == "confirmed":
                continue
            if dispensing.state not in ("draft", "ready"):
                raise UserError(_("Only a draft or POS-ready dispensing can be confirmed."))
            dispensing._validate_prepared_lines()
            dispensing.prescription_id._assign_permanent_number()
            dispensing.write({"state": "confirmed", "dispensed_at": fields.Datetime.now()})
            dispensing.line_ids._snapshot_remaining_balance()
            dispensing._create_register_entries(reversal=False)
            dispensing.prescription_id._update_dispensing_state()
        return True

    def _create_register_entries(self, reversal=False):
        Entry = self.env["pharmacy.register.entry"].sudo().with_context(
            allow_pharmacy_register_create=True,
            skip_pharmacy_audit=True,
        )
        for dispensing in self:
            for line in dispensing.line_ids:
                for register_type in line.product_id.product_tmpl_id.pharmacy_register_type_ids:
                    values = {
                        "register_type_id": register_type.id,
                        "entry_datetime": fields.Datetime.now(),
                        "movement_type": "reversal" if reversal else "dispense",
                        "patient_id": dispensing.patient_id.id,
                        "prescriber_id": dispensing.prescriber_id.id,
                        "prescription_id": dispensing.prescription_id.id,
                        "dispensing_id": dispensing.id,
                        "dispensing_line_id": line.id,
                        "product_id": line.product_id.id,
                        "lot_id": line.lot_id.id,
                        "quantity_in": line.quantity if reversal else 0.0,
                        "quantity_out": 0.0 if reversal else line.quantity,
                        "product_uom_id": line.product_uom_id.id,
                        "pharmacist_id": dispensing.pharmacist_id.id,
                        "source_reference": dispensing.source_reference or dispensing.name,
                        "company_id": dispensing.company_id.id,
                    }
                    Entry.create(values)

    def action_reverse(self):
        for dispensing in self:
            if dispensing.state != "confirmed":
                raise UserError(_("Only confirmed dispensing records can be reversed."))
            if not dispensing.reversal_reason:
                raise UserError(_("Enter a reversal reason before reversing the dispensing record."))
            if not (
                self.env.su
                or self.env.user.has_group("noels_pharmacy.group_pharmacy_manager")
            ):
                raise UserError(_("Only a pharmacy manager can reverse a confirmed dispensing record."))
            dispensing.write(
                {
                    "state": "reversed",
                    "reversed_at": fields.Datetime.now(),
                    "reversed_by_id": self.env.user.id,
                }
            )
            dispensing._create_register_entries(reversal=True)
            dispensing.prescription_id._update_dispensing_state()
        return True

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("Confirmed dispensing records cannot be deleted. Use a documented reversal."))
        return super().unlink()


class PharmacyDispensingLine(models.Model):
    _name = "pharmacy.dispensing.line"
    _description = "Dispensing Line"
    _inherit = ["pharmacy.audit.mixin"]
    _order = "id"

    _pharmacy_audit_fields = (
        "dispensing_id",
        "prescription_line_id",
        "product_id",
        "quantity",
        "product_uom_id",
        "lot_id",
        "expiry_record_id",
        "remaining_after",
        "dispensing_instructions",
        "discard_after",
    )

    dispensing_id = fields.Many2one("pharmacy.dispensing", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="dispensing_id.company_id", store=True, index=True)
    prescription_id = fields.Many2one(
        related="dispensing_id.prescription_id",
        store=True,
        index=True,
    )
    patient_id = fields.Many2one(related="dispensing_id.patient_id", store=True, index=True)
    prescriber_id = fields.Many2one(related="dispensing_id.prescriber_id", store=True, index=True)
    pharmacist_id = fields.Many2one(related="dispensing_id.pharmacist_id", store=True, index=True)
    pharmacist_initials = fields.Char(related="dispensing_id.pharmacist_initials", store=True)
    dispensed_at = fields.Datetime(related="dispensing_id.dispensed_at", store=True, index=True)
    source_type = fields.Selection(related="dispensing_id.source_type", store=True, index=True)
    source_reference = fields.Char(related="dispensing_id.source_reference", store=True, index=True)
    dispensing_state = fields.Selection(
        related="dispensing_id.state",
        string="Status",
        store=True,
        index=True,
    )
    reversal_reason = fields.Text(related="dispensing_id.reversal_reason")
    prescription_line_id = fields.Many2one(
        "pharmacy.prescription.line",
        required=True,
        ondelete="restrict",
        index=True,
    )
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict", index=True)
    quantity = fields.Float(required=True, digits="Product Unit of Measure")
    product_uom_id = fields.Many2one("uom.uom", required=True)
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot / Batch",
        ondelete="restrict",
        domain="[('product_id', '=', product_id)]",
    )
    expiry_record_id = fields.Many2one(
        "pharmacy.expiry.record",
        string="Pharmacy Expiry",
        ondelete="restrict",
        domain="[('product_id', '=', product_id), ('company_id', '=', company_id), ('active', '=', True)]",
    )
    expiry_date = fields.Date(related="expiry_record_id.expiry_date", store=True)
    prescribed_qty = fields.Float(
        related="prescription_line_id.prescribed_qty",
        string="Qty Prescribed per Fill",
    )
    remaining_after = fields.Float(readonly=True, copy=False, digits="Product Unit of Measure")
    dispensing_instructions = fields.Text(required=True)
    discard_after = fields.Date(
        string="Discard / Use By",
        help="Optional patient-facing discard or use-by date printed on the medication label.",
    )

    @api.onchange("product_id")
    def _onchange_product_expiry(self):
        self._assign_default_expiry_records()

    def _assign_default_expiry_records(self):
        Expiry = self.env["pharmacy.expiry.record"]
        for line in self:
            if not line.product_id or line.expiry_record_id:
                continue
            line.expiry_record_id = Expiry.find_earliest_available(
                line.product_id,
                line.company_id or self.env.company,
            )

    @api.constrains("prescription_line_id", "product_id")
    def _check_product_matches(self):
        for line in self:
            allowed = line.prescription_line_id.substituted_product_id or line.prescription_line_id.product_id
            if line.product_id != allowed:
                raise ValidationError(_("The supplied medicine must match the prescribed or approved substitute medicine."))

    def _snapshot_remaining_balance(self):
        for line in self:
            line.with_context(
                skip_pharmacy_audit=True,
                allow_pharmacy_balance_snapshot=True,
            ).write(
                {"remaining_after": line.prescription_line_id.remaining_qty}
            )

    def write(self, values):
        if (
            not self.env.context.get("allow_pharmacy_balance_snapshot")
            and any(line.dispensing_id.state != "draft" for line in self)
        ):
            raise UserError(_("Confirmed dispensing lines are immutable."))
        return super().write(values)

    def unlink(self):
        if any(line.dispensing_id.state != "draft" for line in self):
            raise UserError(_("Confirmed dispensing lines cannot be deleted."))
        return super().unlink()
