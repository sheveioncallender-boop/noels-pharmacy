from odoo import fields, models


class PharmacyStaffProfile(models.Model):
    _name = "pharmacy.staff.profile"
    _description = "Pharmacy Staff Profile"
    _inherit = ["mail.thread", "pharmacy.audit.mixin"]
    _order = "name"

    _pharmacy_audit_fields = (
        "user_id",
        "initials",
        "license_number",
        "role",
        "active",
    )

    user_id = fields.Many2one("res.users", required=True, ondelete="restrict", tracking=True)
    name = fields.Char(related="user_id.name", store=True, index=True)
    initials = fields.Char(required=True, size=10, tracking=True)
    license_number = fields.Char(tracking=True)
    role = fields.Selection(
        [
            ("cashier", "Cashier / Pharmacy Staff"),
            ("technician", "Pharmacy Technician"),
            ("pharmacist", "Pharmacist"),
            ("manager", "Pharmacy Manager"),
        ],
        required=True,
        default="cashier",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True, tracking=True)

    _staff_user_company_unique = models.Constraint(
        "unique(user_id, company_id)",
        "The user already has a pharmacy staff profile in this company.",
    )
    _staff_initials_company_unique = models.Constraint(
        "unique(initials, company_id)",
        "Pharmacist/staff initials must be unique per company.",
    )
