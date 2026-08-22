from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
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
    dispensed_at = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)
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
    line_ids = fields.One2many("pharmacy.dispensing.line", "dispensing_id", copy=True)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("reversed", "Reversed")],
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
        for line in self.prescription_id.line_ids.filtered(lambda item: item.remaining_qty > 0):
            if line.id in existing:
                continue
            commands.append(
                (
                    0,
                    0,
                    {
                        "prescription_line_id": line.id,
                        "product_id": (line.substituted_product_id or line.product_id).id,
                        "quantity": min(line.prescribed_qty, line.remaining_qty),
                        "product_uom_id": line.product_uom_id.id,
                        "dispensing_instructions": line.dispensing_instructions,
                    },
                )
            )
        self.line_ids = commands

    def action_confirm(self):
        for dispensing in self:
            if dispensing.state != "draft":
                continue
            if dispensing.prescription_id.state not in ("approved", "partially_dispensed"):
                raise UserError(_("The prescription must be pharmacist-approved before dispensing."))
            if dispensing.pharmacist_id.role not in ("pharmacist", "manager"):
                raise UserError(_("The confirming staff profile must be a pharmacist or pharmacy manager."))
            if not dispensing.line_ids:
                raise UserError(_("Add at least one medicine to the dispensing record."))
            for line in dispensing.line_ids:
                if line.quantity <= 0:
                    raise UserError(_("Every supplied quantity must be greater than zero."))
                if float_compare(
                    line.quantity,
                    line.prescription_line_id.remaining_qty,
                    precision_rounding=line.product_uom_id.rounding,
                ) > 0:
                    raise UserError(
                        _("The quantity supplied for %s exceeds the remaining authorised balance.")
                        % line.product_id.display_name
                    )
                if line.product_id.tracking != "none" and not line.lot_id:
                    raise UserError(_("Select the supplied lot/batch for %s.") % line.product_id.display_name)
            dispensing.prescription_id._assign_permanent_number()
            dispensing.write({"state": "confirmed"})
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
        "remaining_after",
        "dispensing_instructions",
    )

    dispensing_id = fields.Many2one("pharmacy.dispensing", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="dispensing_id.company_id", store=True, index=True)
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
    remaining_after = fields.Float(readonly=True, copy=False, digits="Product Unit of Measure")
    dispensing_instructions = fields.Text(required=True)

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
