from odoo import models


class PharmacyPatient(models.Model):
    _inherit = "pharmacy.patient"

    def action_print_pharmacy_history(self):
        return self.env.ref("noels_pharmacy.action_report_patient_history").report_action(self)
