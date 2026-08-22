from odoo import fields, models


class PharmacyPrescription(models.Model):
    _inherit = "pharmacy.prescription"

    sale_order_ids = fields.One2many("sale.order", "pharmacy_prescription_id", string="Sales Orders")
    sale_order_count = fields.Integer(compute="_compute_sale_order_count")

    def _compute_sale_order_count(self):
        grouped = self.env["sale.order"]._read_group(
            [("pharmacy_prescription_id", "in", self.ids)],
            ["pharmacy_prescription_id"],
            ["__count"],
        )
        counts = {prescription.id: count for prescription, count in grouped}
        for prescription in self:
            prescription.sale_order_count = counts.get(prescription.id, 0)
