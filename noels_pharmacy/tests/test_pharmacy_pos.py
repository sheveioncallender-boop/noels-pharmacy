from odoo.tests.common import TransactionCase


class TestPharmacyPos(TransactionCase):
    def test_product_fields_are_loaded_in_pos(self):
        fields_list = self.env["product.template"]._load_pos_data_fields(False)
        self.assertIn("is_pharmacy_item", fields_list)
        self.assertIn("pharmacy_rx_required", fields_list)
