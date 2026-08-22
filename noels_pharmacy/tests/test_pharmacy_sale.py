from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestPharmacySale(TransactionCase):
    def setUp(self):
        super().setUp()
        self.customer = self.env["res.partner"].create({"name": "Sale Test Patient"})
        template = self.env["product.template"].create(
            {
                "name": "Prescription Sale Medicine",
                "is_pharmacy_item": True,
                "pharmacy_rx_required": True,
                "pharmacy_default_directions": "Take one daily",
            }
        )
        self.product = template.product_variant_id

    def test_regulated_sale_requires_prescription(self):
        order = self.env["sale.order"].create({"partner_id": self.customer.id})
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 1,
            }
        )
        self.assertTrue(order.pharmacy_requires_prescription)
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_create_prescription_from_sale(self):
        order = self.env["sale.order"].create({"partner_id": self.customer.id})
        self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "product_uom_qty": 2,
                "pharmacy_dispensing_instructions": "Take two with food",
            }
        )
        order.action_create_pharmacy_prescription()
        self.assertTrue(order.pharmacy_prescription_id)
        self.assertEqual(order.pharmacy_prescription_id.line_ids.prescribed_qty, 2)
