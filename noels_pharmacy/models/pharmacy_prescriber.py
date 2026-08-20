from odoo import fields, models


class PharmacyPrescriber(models.Model):
    _name = "pharmacy.prescriber"
    _description = "Pharmacy Prescriber"
    _inherit = ["mail.thread", "mail.activity.mixin", "pharmacy.audit.mixin"]
    _order = "name"

    _pharmacy_audit_fields = (
        "partner_id",
        "license_number",
        "specialty",
        "active",
    )

    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True)
    name = fields.Char(related="partner_id.name", store=True, index=True)
    license_number = fields.Char(
        index=True,
        tracking=True,
        help="Record the professional licence/registration number when it is available.",
    )
    specialty = fields.Char(tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    notes = fields.Text()

    _prescriber_license_company_unique = models.Constraint(
        "unique(license_number, company_id)",
        "The prescriber licence number must be unique per company.",
    )
