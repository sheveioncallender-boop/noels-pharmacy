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
        "follow_up_status",
        "follow_up_date",
        "follow_up_count",
        "last_follow_up_at",
        "last_follow_up_by_id",
        "follow_up_notes",
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
    patient_phone = fields.Char(related="patient_id.phone", string="Patient Phone")
    patient_mobile = fields.Char(related="patient_id.mobile", string="Patient Mobile")
    patient_email = fields.Char(related="patient_id.email", string="Patient Email")
    patient_allergy_status = fields.Selection(
        related="patient_id.allergy_status",
        string="Allergy Status",
    )
    patient_allergy_summary = fields.Char(compute="_compute_patient_allergy_summary")
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
    remaining_total_qty = fields.Float(
        compute="_compute_follow_up_summary",
        string="Total Quantity Remaining",
        digits="Product Unit of Measure",
    )
    partial_fill_open = fields.Boolean(compute="_compute_follow_up_summary", store=True, index=True)
    partial_fill_remaining_qty = fields.Float(
        compute="_compute_follow_up_summary",
        store=True,
        string="Partial Fill Balance",
        digits="Product Unit of Measure",
    )
    outstanding_medicines = fields.Char(compute="_compute_follow_up_summary")
    last_dispensed_at = fields.Datetime(compute="_compute_follow_up_summary")
    follow_up_status = fields.Selection(
        [
            ("not_required", "Not Required"),
            ("pending", "Follow-up Pending"),
            ("contacted", "Patient Contacted"),
            ("completed", "Completed"),
        ],
        required=True,
        default="not_required",
        copy=False,
        index=True,
        tracking=True,
    )
    follow_up_date = fields.Date(string="Follow-up Due", copy=False, tracking=True)
    follow_up_count = fields.Integer(readonly=True, copy=False, default=0)
    last_follow_up_at = fields.Datetime(readonly=True, copy=False)
    last_follow_up_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    follow_up_notes = fields.Text(copy=False, tracking=True)
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
            if not self.prescriber_id and self.patient_id.primary_doctor_id:
                self.prescriber_id = self.patient_id.primary_doctor_id

    @api.depends(
        "patient_id.allergy_status",
        "patient_id.allergy_ids.active",
        "patient_id.allergy_ids.allergen_name",
        "patient_id.allergy_ids.severity",
    )
    def _compute_patient_allergy_summary(self):
        for prescription in self:
            allergies = prescription.patient_id.allergy_ids.filtered("active")
            if prescription.patient_id.allergy_status == "none":
                prescription.patient_allergy_summary = _("No Known Drug Allergies")
            elif allergies:
                prescription.patient_allergy_summary = ", ".join(
                    "%s (%s)" % (
                        allergy.allergen_name,
                        dict(allergy._fields["severity"].selection).get(allergy.severity),
                    )
                    for allergy in allergies
                )
            else:
                prescription.patient_allergy_summary = _("Allergy status not confirmed")

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

    @api.depends(
        "line_ids.remaining_qty",
        "line_ids.partial_fill_qty",
        "line_ids.product_id",
        "dispensing_ids.state",
        "dispensing_ids.dispensed_at",
    )
    def _compute_follow_up_summary(self):
        for prescription in self:
            remaining_lines = prescription.line_ids.filtered(lambda line: line.remaining_qty > 0)
            prescription.remaining_total_qty = sum(remaining_lines.mapped("remaining_qty"))
            partial_lines = prescription.line_ids.filtered(lambda line: line.partial_fill_qty > 0)
            prescription.partial_fill_open = bool(partial_lines)
            prescription.partial_fill_remaining_qty = sum(partial_lines.mapped("partial_fill_qty"))
            prescription.outstanding_medicines = ", ".join(
                "%s: %s" % (line.product_id.display_name, line.partial_fill_qty)
                for line in partial_lines
            )
            confirmed_dates = prescription.dispensing_ids.filtered(
                lambda dispensing: dispensing.state == "confirmed" and dispensing.dispensed_at
            ).mapped("dispensed_at")
            prescription.last_dispensed_at = max(confirmed_dates, default=False)

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
            values = {"state": target}
            if target == "partially_dispensed":
                for line in remaining:
                    next_quantity = line.partial_fill_qty or min(
                        line.prescribed_qty,
                        line.remaining_qty,
                    )
                    line.with_context(allow_pharmacy_supply_quantity=True).write(
                        {"quantity_to_supply": next_quantity}
                    )
                if prescription.partial_fill_open:
                    values["follow_up_status"] = "pending"
                    values["follow_up_date"] = fields.Date.add(
                        fields.Date.context_today(prescription),
                        days=2,
                    )
                else:
                    values.update(
                        {
                            "follow_up_status": "not_required",
                            "follow_up_date": False,
                        }
                    )
            elif target == "dispensed":
                values.update(
                    {
                        "follow_up_status": "completed",
                        "follow_up_date": False,
                    }
                )
            prescription.with_context(skip_pharmacy_state_guard=True).write(values)

    def _record_follow_up(self, channel):
        now = fields.Datetime.now()
        for prescription in self:
            if prescription.state != "partially_dispensed":
                raise UserError(_("Follow-up is only available for partially filled prescriptions."))
            if not prescription.partial_fill_open:
                raise UserError(_("This prescription has refill balance, but no partially supplied fill to follow up."))
            prescription.write(
                {
                    "follow_up_status": "contacted",
                    "follow_up_count": prescription.follow_up_count + 1,
                    "last_follow_up_at": now,
                    "last_follow_up_by_id": self.env.user.id,
                }
            )
            prescription.message_post(
                body=_("Partial-fill follow-up recorded by %s using %s. Outstanding: %s")
                % (
                    self.env.user.display_name,
                    channel,
                    prescription.outstanding_medicines,
                ),
                subtype_xmlid="mail.mt_note",
            )
        return True

    def action_mark_follow_up_contacted(self):
        return self._record_follow_up(_("Phone / WhatsApp"))

    def action_send_partial_fill_notification(self):
        template = self.env.ref("noels_pharmacy.mail_template_partial_fill_notification")
        for prescription in self:
            if not prescription.patient_email:
                raise UserError(_("Add an email address to the patient before sending a notification."))
            template.send_mail(prescription.id, force_send=True)
        return self._record_follow_up(_("Email"))

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

    def _get_or_create_prepared_dispensing(self):
        self.ensure_one()
        existing = self.dispensing_ids.filtered(
            lambda dispensing: dispensing.state in ("draft", "ready")
        ).sorted("id", reverse=True)[:1]
        if existing:
            if existing.state == "draft":
                existing.line_ids._assign_default_expiry_records()
            return existing
        staff = self._current_staff_profile()
        if not staff or staff.role not in ("pharmacist", "manager"):
            raise UserError(_("An active pharmacist or pharmacy manager profile is required."))
        commands = []
        Expiry = self.env["pharmacy.expiry.record"]
        lines_to_prepare = self.line_ids.filtered(
            lambda item: item.remaining_qty > 0
            and (not self.partial_fill_open or item.partial_fill_qty > 0)
            and item.quantity_to_supply > 0
        )
        for line in lines_to_prepare:
            product = line.substituted_product_id or line.product_id
            expiry = Expiry.find_earliest_available(product, self.company_id)
            commands.append(
                fields.Command.create(
                    {
                        "prescription_line_id": line.id,
                        "product_id": product.id,
                        "quantity": min(
                            line.quantity_to_supply,
                            line.partial_fill_qty or line.remaining_qty,
                        ),
                        "product_uom_id": line.product_uom_id.id,
                        "dispensing_instructions": line.dispensing_instructions,
                        "expiry_record_id": expiry.id,
                    }
                )
            )
        if not commands:
            raise UserError(_("This prescription has no remaining quantity to prepare."))
        return self.env["pharmacy.dispensing"].create(
            {
                "prescription_id": self.id,
                "pharmacist_id": staff.id,
                "source_type": "pos",
                "line_ids": commands,
            }
        )

    def action_approve_prepare_print(self):
        """Single backend operation: clinical review, preparation, POS barcode and labels."""
        self.ensure_one()
        if self.state == "draft":
            self.action_submit()
        if self.state == "awaiting_review":
            self.action_approve()
        if self.state not in ("approved", "partially_dispensed"):
            raise UserError(_("This prescription cannot be prepared in its current status."))
        dispensing = self._get_or_create_prepared_dispensing()
        if dispensing.state == "ready":
            return dispensing.action_print_labels()
        return dispensing.action_ready_for_pos()

    def action_prepare_balance_and_print(self):
        return self.action_approve_prepare_print()

    def action_prepare_for_pos(self):
        self.ensure_one()
        if self.state not in ("approved", "partially_dispensed"):
            raise UserError(_("Approve the prescription before preparing it for POS."))
        dispensing = self._get_or_create_prepared_dispensing()
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
        "quantity_to_supply",
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
    quantity_to_supply = fields.Float(
        string="Supply Now",
        default=1.0,
        digits="Product Unit of Measure",
        help="Quantity to prepare now. Use a smaller quantity for a short fill, or zero when this medicine is unavailable today.",
    )
    product_uom_id = fields.Many2one("uom.uom", required=True)
    refills_allowed = fields.Integer(related="prescription_id.refills_allowed", store=True)
    authorized_qty = fields.Float(compute="_compute_quantities", store=True, digits="Product Unit of Measure")
    qty_dispensed = fields.Float(compute="_compute_quantities", store=True, digits="Product Unit of Measure")
    remaining_qty = fields.Float(compute="_compute_quantities", store=True, digits="Product Unit of Measure")
    partial_fill_qty = fields.Float(
        compute="_compute_quantities",
        store=True,
        string="Open Partial Balance",
        digits="Product Unit of Measure",
    )
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
        "prescription_id.dispensing_ids.state",
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
            confirmed_fill_exists = bool(
                line.prescription_id.dispensing_ids.filtered(
                    lambda dispensing: dispensing.state == "confirmed"
                )
            )
            if line.prescribed_qty and line.qty_dispensed:
                completed_fills = int(line.qty_dispensed / line.prescribed_qty)
                current_fill_supplied = line.qty_dispensed - (completed_fills * line.prescribed_qty)
                if float_is_zero(
                    current_fill_supplied,
                    precision_rounding=line.product_uom_id.rounding,
                ):
                    line.partial_fill_qty = 0.0
                else:
                    line.partial_fill_qty = min(
                        line.prescribed_qty - current_fill_supplied,
                        line.remaining_qty,
                    )
            elif confirmed_fill_exists and line.remaining_qty:
                line.partial_fill_qty = min(line.prescribed_qty, line.remaining_qty)
            else:
                line.partial_fill_qty = 0.0

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

    @api.onchange("prescribed_qty")
    def _onchange_prescribed_qty(self):
        if self.prescribed_qty:
            self.quantity_to_supply = self.prescribed_qty

    @api.onchange("dispensing_instructions")
    def _onchange_dispensing_instructions(self):
        if self.dispensing_instructions:
            self.directions_pending = False

    @api.constrains("prescribed_qty", "quantity_to_supply")
    def _check_prescribed_qty(self):
        if any(line.prescribed_qty <= 0 for line in self):
            raise ValidationError(_("Prescribed quantity must be greater than zero."))
        if any(line.quantity_to_supply < 0 for line in self):
            raise ValidationError(_("Supply Now cannot be negative."))

    @api.constrains("substituted_product_id", "substitution_reason")
    def _check_substitution_reason(self):
        for line in self:
            if line.substituted_product_id and not line.substitution_reason:
                raise ValidationError(_("Record the reason for every medicine substitution."))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if not values.get("quantity_to_supply") and values.get("prescribed_qty"):
                values["quantity_to_supply"] = values["prescribed_qty"]
        prescriptions = self.env["pharmacy.prescription"].browse(
            [values.get("prescription_id") for values in vals_list if values.get("prescription_id")]
        )
        if any(record.state != "draft" for record in prescriptions):
            raise UserError(_("Medicines can only be added while the prescription is in Draft."))
        return super().create(vals_list)

    def write(self, values):
        supply_only = set(values) <= {"quantity_to_supply"}
        allowed_partial = supply_only and all(
            line.prescription_id.state == "partially_dispensed" for line in self
        )
        if (
            not self.env.context.get("allow_pharmacy_supply_quantity")
            and not allowed_partial
            and any(line.prescription_id.state != "draft" for line in self)
        ):
            raise UserError(_("Return the prescription to Draft before changing medicine lines."))
        return super().write(values)

    def unlink(self):
        if any(line.prescription_id.state != "draft" for line in self):
            raise UserError(_("Medicine lines on reviewed prescriptions cannot be deleted."))
        return super().unlink()
