from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_is_zero


class PharmacyPrescription(models.Model):
    _name = "pharmacy.prescription"
    _description = "Pharmacy Prescription"
    _inherit = ["mail.thread", "mail.activity.mixin", "pharmacy.audit.mixin"]
    _order = "prescription_date desc, id desc"

    _pharmacy_audit_fields = (
        "name",
        "patient_id",
        "purchaser_partner_id",
        "prescriber_id",
        "prescription_date",
        "valid_until",
        "external_reference",
        "source_type",
        "diagnosis_notes",
        "refills_allowed",
        "state",
        "approved_by_id",
        "approved_at",
        "cancellation_reason",
    )

    name = fields.Char(
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        index=True,
        tracking=True,
    )
    temporary_reference = fields.Char(readonly=True, copy=False, index=True)
    patient_id = fields.Many2one(
        "pharmacy.patient",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    purchaser_partner_id = fields.Many2one(
        "res.partner",
        string="Purchaser / Representative",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    prescriber_id = fields.Many2one(
        "pharmacy.prescriber",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    prescription_date = fields.Date(
        required=True,
        default=fields.Date.context_today,
        index=True,
        tracking=True,
    )
    valid_until = fields.Date(tracking=True)
    external_reference = fields.Char(string="Prescriber's Reference", tracking=True)
    source_type = fields.Selection(
        [
            ("physical", "Physical Prescription"),
            ("whatsapp", "WhatsApp Image"),
            ("email", "Email PDF"),
            ("printed", "Printed Script"),
            ("website", "Website Upload"),
            ("other", "Other"),
        ],
        required=True,
        default="physical",
        tracking=True,
    )
    diagnosis_notes = fields.Text(string="Diagnosis / Notes", tracking=True)
    refills_allowed = fields.Integer(default=0, tracking=True)
    line_ids = fields.One2many(
        "pharmacy.prescription.line",
        "prescription_id",
        string="Medicines",
        copy=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "pharmacy_prescription_attachment_rel",
        "prescription_id",
        "attachment_id",
        string="Prescription Documents",
        copy=False,
        groups="noels_pharmacy.group_pharmacy_user",
    )
    clinical_alert_ids = fields.One2many("pharmacy.clinical.alert", "prescription_id")
    dispensing_ids = fields.One2many("pharmacy.dispensing", "prescription_id")
    dispensing_count = fields.Integer(compute="_compute_dispensing_count")
    alert_count = fields.Integer(compute="_compute_alert_count")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("awaiting_review", "Awaiting Review"),
            ("approved", "Approved"),
            ("partially_dispensed", "Partially Dispensed / Refill Available"),
            ("dispensed", "Dispensed"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one("pharmacy.staff.profile", readonly=True, copy=False, tracking=True)
    approved_at = fields.Datetime(readonly=True, copy=False, tracking=True)
    cancellation_reason = fields.Text(copy=False, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True)

    _refills_nonnegative = models.Constraint(
        "check(refills_allowed >= 0)",
        "Refills allowed cannot be negative.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            temporary = self.env["ir.sequence"].next_by_code("noels.pharmacy.prescription.temp")
            values.setdefault("temporary_reference", temporary)
            if values.get("name", _("New")) == _("New"):
                values["name"] = temporary
            if values.get("patient_id") and not values.get("purchaser_partner_id"):
                patient = self.env["pharmacy.patient"].browse(values["patient_id"])
                values["purchaser_partner_id"] = patient.partner_id.id
        return super().create(vals_list)

    @api.onchange("patient_id")
    def _onchange_patient_id(self):
        if self.patient_id:
            self.purchaser_partner_id = self.patient_id.partner_id

    @api.depends("dispensing_ids")
    def _compute_dispensing_count(self):
        counts = self.env["pharmacy.dispensing"]._read_group(
            [("prescription_id", "in", self.ids)],
            ["prescription_id"],
            ["__count"],
        )
        mapped = {prescription.id: count for prescription, count in counts}
        for prescription in self:
            prescription.dispensing_count = mapped.get(prescription.id, 0)

    @api.depends("clinical_alert_ids", "clinical_alert_ids.status")
    def _compute_alert_count(self):
        for prescription in self:
            prescription.alert_count = len(
                prescription.clinical_alert_ids.filtered(lambda alert: alert.status != "superseded")
            )

    @api.constrains("prescription_date", "valid_until")
    def _check_valid_until(self):
        for prescription in self:
            if prescription.valid_until and prescription.valid_until < prescription.prescription_date:
                raise ValidationError(_("The prescription valid-until date cannot precede its issue date."))

    def write(self, values):
        protected = {
            "patient_id",
            "purchaser_partner_id",
            "prescriber_id",
            "prescription_date",
            "valid_until",
            "external_reference",
            "source_type",
            "refills_allowed",
        }
        if protected.intersection(values) and any(record.state != "draft" for record in self):
            raise UserError(_("Return the prescription to Draft before changing its clinical details."))
        return super().write(values)

    def _validate_for_review(self):
        for prescription in self:
            if not prescription.line_ids:
                raise UserError(_("Add at least one medicine before submitting the prescription."))
            regulated = prescription.line_ids.filtered(
                lambda line: line.product_id.product_tmpl_id.pharmacy_rx_required
            )
            if regulated and not prescription.prescriber_id:
                raise UserError(_("A prescriber is required for prescription medicines."))
            missing_directions = prescription.line_ids.filtered(
                lambda line: not line.dispensing_instructions or line.directions_pending
            )
            if missing_directions:
                raise UserError(_("Confirm the dispensing instructions for every medicine before review."))

    def action_submit(self):
        for prescription in self:
            if prescription.state != "draft":
                continue
            prescription._validate_for_review()
            prescription.action_run_clinical_checks()
            prescription.write({"state": "awaiting_review"})
        return True

    def _current_staff_profile(self):
        self.ensure_one()
        return self.env["pharmacy.staff.profile"].search(
            [
                ("user_id", "=", self.env.user.id),
                ("company_id", "=", self.company_id.id),
                ("active", "=", True),
            ],
            limit=1,
        )

    def action_approve(self):
        for prescription in self:
            if prescription.state != "awaiting_review":
                raise UserError(_("Only prescriptions awaiting review can be approved."))
            staff = prescription._current_staff_profile()
            if not staff or staff.role not in ("pharmacist", "manager"):
                raise UserError(_("An active pharmacist or pharmacy manager profile is required."))
            blocking = prescription.clinical_alert_ids.filtered(
                lambda alert: alert.severity == "blocking"
                and alert.status in ("open", "acknowledged")
            )
            if blocking:
                raise UserError(_("Resolve or formally override all blocking clinical alerts before approval."))
            prescription.write(
                {
                    "state": "approved",
                    "approved_by_id": staff.id,
                    "approved_at": fields.Datetime.now(),
                }
            )
        return True

    def action_reset_to_draft(self):
        for prescription in self:
            if prescription.state not in ("awaiting_review", "approved"):
                raise UserError(_("Only un-dispensed prescriptions can return to Draft."))
            if prescription.dispensing_ids.filtered(lambda record: record.state == "confirmed"):
                raise UserError(_("A prescription with confirmed dispensing cannot return to Draft."))
            if prescription.dispensing_ids.filtered(lambda record: record.state == "ready"):
                raise UserError(_("Return the prepared fill to Draft before changing this prescription."))
            prescription.write(
                {
                    "state": "draft",
                    "approved_by_id": False,
                    "approved_at": False,
                }
            )
        return True

    def action_cancel(self):
        for prescription in self:
            if not prescription.cancellation_reason:
                raise UserError(_("Enter a cancellation reason before cancelling the prescription."))
            if prescription.dispensing_ids.filtered(lambda record: record.state == "confirmed"):
                raise UserError(_("Reverse confirmed dispensing records before cancelling the prescription."))
            if prescription.dispensing_ids.filtered(lambda record: record.state == "ready"):
                raise UserError(_("Return the POS-ready fill to preparation before cancelling the prescription."))
            if prescription.dispensing_ids.filtered(lambda record: record.state == "draft"):
                raise UserError(_("Delete or complete draft dispensing preparations before cancelling the prescription."))
            prescription.write({"state": "cancelled"})
        return True

    def _assign_permanent_number(self):
        for prescription in self:
            if prescription.name == prescription.temporary_reference:
                permanent = self.env["ir.sequence"].next_by_code("noels.pharmacy.prescription")
                if not permanent:
                    raise UserError(_("The prescription sequence is not configured."))
                prescription.write({"name": permanent})

    def _update_dispensing_state(self):
        for prescription in self:
            if prescription.state == "cancelled":
                continue
            remaining = prescription.line_ids.filtered(
                lambda line: not float_is_zero(
                    line.remaining_qty,
                    precision_rounding=line.product_uom_id.rounding,
                )
            )
            confirmed = prescription.dispensing_ids.filtered(lambda record: record.state == "confirmed")
            if not confirmed:
                target = "approved" if prescription.approved_by_id else "awaiting_review"
            elif remaining:
                target = "partially_dispensed"
            else:
                target = "dispensed"
            prescription.with_context(skip_pharmacy_state_guard=True).write({"state": target})

    def action_view_dispensing(self):
        self.ensure_one()
        action = self.env.ref("noels_pharmacy.action_pharmacy_dispensing").read()[0]
        action["domain"] = [("prescription_id", "=", self.id)]
        action["context"] = {"default_prescription_id": self.id}
        return action

    def action_view_alerts(self):
        self.ensure_one()
        action = self.env.ref("noels_pharmacy.action_pharmacy_clinical_alert").read()[0]
        action["domain"] = [("prescription_id", "=", self.id)]
        return action

    def action_print_labels(self):
        self.ensure_one()
        prepared = self.dispensing_ids.filtered(
            lambda dispensing: dispensing.state in ("ready", "confirmed")
        ).sorted("id", reverse=True)[:1]
        if not prepared:
            raise UserError(_("Prepare this prescription for POS before printing medication labels."))
        return prepared.action_print_labels()

    def action_prepare_for_pos(self):
        self.ensure_one()
        if self.state not in ("approved", "partially_dispensed"):
            raise UserError(_("Approve the prescription before preparing it for POS."))
        existing = self.dispensing_ids.filtered(lambda dispensing: dispensing.state == "ready")[:1]
        if existing:
            return {
                "type": "ir.actions.act_window",
                "name": _("Prepared Fill"),
                "res_model": "pharmacy.dispensing",
                "view_mode": "form",
                "res_id": existing.id,
            }
        staff = self._current_staff_profile()
        if not staff or staff.role not in ("pharmacist", "manager"):
            raise UserError(_("An active pharmacist or pharmacy manager profile is required."))
        commands = []
        for line in self.line_ids.filtered(lambda item: item.remaining_qty > 0):
            commands.append(
                fields.Command.create(
                    {
                        "prescription_line_id": line.id,
                        "product_id": (line.substituted_product_id or line.product_id).id,
                        "quantity": min(line.prescribed_qty, line.remaining_qty),
                        "product_uom_id": line.product_uom_id.id,
                        "dispensing_instructions": line.dispensing_instructions,
                    }
                )
            )
        if not commands:
            raise UserError(_("This prescription has no remaining quantity to prepare."))
        dispensing = self.env["pharmacy.dispensing"].create(
            {
                "prescription_id": self.id,
                "pharmacist_id": staff.id,
                "source_type": "pos",
                "line_ids": commands,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Prepare Prescription for POS"),
            "res_model": "pharmacy.dispensing",
            "view_mode": "form",
            "res_id": dispensing.id,
        }

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("Only draft prescriptions can be deleted. Cancel confirmed records instead."))
        return super().unlink()


class PharmacyPrescriptionLine(models.Model):
    _name = "pharmacy.prescription.line"
    _description = "Prescription Medicine"
    _inherit = ["pharmacy.audit.mixin"]
    _order = "sequence, id"

    _pharmacy_audit_fields = (
        "prescription_id",
        "product_id",
        "prescribed_qty",
        "product_uom_id",
        "dose",
        "route",
        "frequency",
        "duration",
        "dispensing_instructions",
        "directions_pending",
        "caution_instructions",
        "substituted_product_id",
        "substitution_reason",
    )

    sequence = fields.Integer(default=10)
    prescription_id = fields.Many2one(
        "pharmacy.prescription",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="prescription_id.company_id", store=True, index=True)
    product_id = fields.Many2one(
        "product.product",
        string="Prescribed Medicine",
        required=True,
        ondelete="restrict",
        domain="[('product_tmpl_id.is_pharmacy_item', '=', True)]",
    )
    substituted_product_id = fields.Many2one(
        "product.product",
        string="Medicine Supplied Instead",
        ondelete="restrict",
        domain="[('product_tmpl_id.is_pharmacy_item', '=', True)]",
    )
    substitution_reason = fields.Char()
    prescribed_qty = fields.Float(required=True, default=1.0, digits="Product Unit of Measure")
    product_uom_id = fields.Many2one("uom.uom", required=True)
    refills_allowed = fields.Integer(related="prescription_id.refills_allowed", store=True)
    authorized_qty = fields.Float(compute="_compute_quantities", store=True, digits="Product Unit of Measure")
    qty_dispensed = fields.Float(compute="_compute_quantities", store=True, digits="Product Unit of Measure")
    remaining_qty = fields.Float(compute="_compute_quantities", store=True, digits="Product Unit of Measure")
    dispensing_line_ids = fields.One2many("pharmacy.dispensing.line", "prescription_line_id")
    dose = fields.Char()
    route = fields.Selection(
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
        ]
    )
    frequency = fields.Char()
    duration = fields.Char()
    dispensing_instructions = fields.Text(required=True)
    directions_pending = fields.Boolean(
        string="Directions Need Confirmation",
        default=False,
        help="The directions were prefilled and must be checked against the prescription before review.",
    )
    caution_instructions = fields.Text()

    @api.depends(
        "prescribed_qty",
        "refills_allowed",
        "dispensing_line_ids.quantity",
        "dispensing_line_ids.dispensing_id.state",
    )
    def _compute_quantities(self):
        for line in self:
            line.authorized_qty = line.prescribed_qty * (1 + max(line.refills_allowed, 0))
            line.qty_dispensed = sum(
                line.dispensing_line_ids.filtered(
                    lambda dispensing_line: dispensing_line.dispensing_id.state == "confirmed"
                ).mapped("quantity")
            )
            line.remaining_qty = max(line.authorized_qty - line.qty_dispensed, 0.0)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if not self.product_id:
            return
        template = self.product_id.product_tmpl_id
        self.product_uom_id = self.product_id.uom_id
        self.route = template.pharmacy_default_route
        self.dispensing_instructions = template.pharmacy_default_directions
        self.directions_pending = True
        self.caution_instructions = template.pharmacy_default_caution

    @api.onchange("dispensing_instructions")
    def _onchange_dispensing_instructions(self):
        if self.dispensing_instructions:
            self.directions_pending = False

    @api.constrains("prescribed_qty")
    def _check_prescribed_qty(self):
        if any(line.prescribed_qty <= 0 for line in self):
            raise ValidationError(_("Prescribed quantity must be greater than zero."))

    @api.constrains("substituted_product_id", "substitution_reason")
    def _check_substitution_reason(self):
        for line in self:
            if line.substituted_product_id and not line.substitution_reason:
                raise ValidationError(_("Record the reason for every medicine substitution."))

    @api.model_create_multi
    def create(self, vals_list):
        prescriptions = self.env["pharmacy.prescription"].browse(
            [values.get("prescription_id") for values in vals_list if values.get("prescription_id")]
        )
        if any(record.state != "draft" for record in prescriptions):
            raise UserError(_("Medicines can only be added while the prescription is in Draft."))
        return super().create(vals_list)

    def write(self, values):
        if any(line.prescription_id.state != "draft" for line in self):
            raise UserError(_("Return the prescription to Draft before changing medicine lines."))
        return super().write(values)

    def unlink(self):
        if any(line.prescription_id.state != "draft" for line in self):
            raise UserError(_("Medicine lines on reviewed prescriptions cannot be deleted."))
        return super().unlink()
