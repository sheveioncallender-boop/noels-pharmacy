from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PharmacyPatient(models.Model):
    _name = "pharmacy.patient"
    _description = "Pharmacy Patient"
    _inherit = ["mail.thread", "mail.activity.mixin", "pharmacy.audit.mixin"]
    _order = "name"

    _pharmacy_audit_fields = (
        "partner_id",
        "date_of_birth",
        "allergy_status",
        "guardian_partner_id",
        "active",
    )

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    name = fields.Char(related="partner_id.name", store=True, index=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    date_of_birth = fields.Date(tracking=True)
    age = fields.Integer(compute="_compute_age")
    guardian_partner_id = fields.Many2one(
        "res.partner",
        string="Parent / Guardian / Caregiver",
        tracking=True,
    )
    allergy_status = fields.Selection(
        [
            ("unknown", "Not Confirmed"),
            ("none", "No Known Drug Allergies"),
            ("known", "Known Allergies"),
        ],
        required=True,
        default="unknown",
        tracking=True,
    )
    allergy_ids = fields.One2many("pharmacy.patient.allergy", "patient_id", string="Allergies")
    prescription_ids = fields.One2many("pharmacy.prescription", "patient_id")
    prescription_count = fields.Integer(compute="_compute_prescription_count")
    notes = fields.Text(groups="noels_pharmacy.group_pharmacy_pharmacist")

    _patient_partner_company_unique = models.Constraint(
        "unique(partner_id, company_id)",
        "This contact already has a patient profile in the selected company.",
    )

    @api.depends("date_of_birth")
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for patient in self:
            patient.age = relativedelta(today, patient.date_of_birth).years if patient.date_of_birth else 0

    @api.depends("prescription_ids")
    def _compute_prescription_count(self):
        counts = self.env["pharmacy.prescription"]._read_group(
            [("patient_id", "in", self.ids)],
            ["patient_id"],
            ["__count"],
        )
        mapped = {patient.id: count for patient, count in counts}
        for patient in self:
            patient.prescription_count = mapped.get(patient.id, 0)

    def action_view_prescriptions(self):
        self.ensure_one()
        action = self.env.ref("noels_pharmacy.action_pharmacy_prescription").read()[0]
        action["domain"] = [("patient_id", "=", self.id)]
        action["context"] = {"default_patient_id": self.id}
        return action

    def unlink(self):
        if any(patient.prescription_ids for patient in self):
            raise UserError(_("A patient with prescription history cannot be deleted. Archive the patient instead."))
        return super().unlink()


class PharmacyPatientAllergy(models.Model):
    _name = "pharmacy.patient.allergy"
    _description = "Patient Allergy"
    _inherit = ["pharmacy.audit.mixin"]
    _order = "active desc, id desc"

    _pharmacy_audit_fields = (
        "patient_id",
        "ingredient_id",
        "allergen_name",
        "reaction",
        "severity",
        "active",
    )

    patient_id = fields.Many2one("pharmacy.patient", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="patient_id.company_id", store=True, index=True)
    ingredient_id = fields.Many2one("pharmacy.active.ingredient", string="Active Ingredient", index=True)
    allergen_name = fields.Char(required=True)
    reaction = fields.Char()
    severity = fields.Selection(
        [("mild", "Mild"), ("moderate", "Moderate"), ("severe", "Severe")],
        default="moderate",
        required=True,
    )
    active = fields.Boolean(default=True)
    noted_date = fields.Date(default=fields.Date.context_today)
    notes = fields.Text()

    @api.onchange("ingredient_id")
    def _onchange_ingredient_id(self):
        if self.ingredient_id:
            self.allergen_name = self.ingredient_id.name
