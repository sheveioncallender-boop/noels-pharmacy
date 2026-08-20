from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    pharmacy_patient_profile_ids = fields.One2many(
        "pharmacy.patient",
        "partner_id",
        string="Pharmacy Patient Profiles",
    )
    pharmacy_patient_count = fields.Integer(compute="_compute_pharmacy_patient_count")
    pharmacy_purchased_prescription_ids = fields.One2many(
        "pharmacy.prescription",
        "purchaser_partner_id",
        string="Prescription Purchases",
    )
    pharmacy_purchased_prescription_count = fields.Integer(
        compute="_compute_pharmacy_purchased_prescription_count"
    )

    def _compute_pharmacy_patient_count(self):
        for partner in self:
            partner.pharmacy_patient_count = len(
                partner.pharmacy_patient_profile_ids.filtered(
                    lambda patient: patient.company_id == self.env.company
                )
            )

    def action_open_pharmacy_patient(self):
        self.ensure_one()
        patient = self.pharmacy_patient_profile_ids.filtered(
            lambda profile: profile.company_id == self.env.company
        )[:1]
        if not patient:
            patient = self.env["pharmacy.patient"].create(
                {
                    "partner_id": self.id,
                    "company_id": self.env.company.id,
                }
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Patient Profile",
            "res_model": "pharmacy.patient",
            "view_mode": "form",
            "res_id": patient.id,
            "target": "current",
        }

    def _compute_pharmacy_purchased_prescription_count(self):
        grouped = self.env["pharmacy.prescription"]._read_group(
            [("purchaser_partner_id", "in", self.ids)],
            ["purchaser_partner_id"],
            ["__count"],
        )
        counts = {partner.id: count for partner, count in grouped}
        for partner in self:
            partner.pharmacy_purchased_prescription_count = counts.get(partner.id, 0)

    def action_view_pharmacy_purchased_prescriptions(self):
        self.ensure_one()
        action = self.env.ref("noels_pharmacy.action_pharmacy_prescription").read()[0]
        action["domain"] = [("purchaser_partner_id", "=", self.id)]
        action["context"] = {"default_purchaser_partner_id": self.id}
        return action
