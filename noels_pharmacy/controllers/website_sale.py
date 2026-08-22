from odoo import _
from odoo.addons.website_sale.controllers.main import WebsiteSale


class PharmacyWebsiteSale(WebsiteSale):
    def _get_shop_payment_errors(self, order):
        errors = super()._get_shop_payment_errors(order)
        if not order.pharmacy_requires_prescription:
            return errors
        prescription = order.pharmacy_prescription_id
        if not prescription:
            errors.append(
                (
                    _("Prescription required"),
                    _("Sign in and upload the prescription from your cart before payment."),
                )
            )
        elif prescription.state not in ("approved", "partially_dispensed"):
            errors.append(
                (
                    _("Prescription review pending"),
                    _("A pharmacist must approve the uploaded prescription before payment."),
                )
            )
        return errors
