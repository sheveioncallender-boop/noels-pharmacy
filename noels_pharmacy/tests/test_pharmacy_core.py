from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNoelsPharmacyCore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "John Mohammed"})
        cls.patient = cls.env["pharmacy.patient"].create(
            {
                "partner_id": cls.partner.id,
                "allergy_status": "none",
            }
        )
        cls.doctor_partner = cls.env["res.partner"].create({"name": "Dr. Singh"})
        cls.prescriber = cls.env["pharmacy.prescriber"].create(
            {
                "partner_id": cls.doctor_partner.id,
                "license_number": "MED-2841",
            }
        )
        cls.staff = cls.env["pharmacy.staff.profile"].create(
            {
                "user_id": cls.env.user.id,
                "initials": "SC",
                "license_number": "PHARM-001",
                "role": "pharmacist",
            }
        )
        cls.ingredient = cls.env["pharmacy.active.ingredient"].create(
            {"name": "Amoxicillin"}
        )
        cls.product_template = cls.env["product.template"].create(
            {
                "name": "Amoxicillin 500 mg",
                "is_pharmacy_item": True,
                "pharmacy_generic_name": "Amoxicillin",
                "pharmacy_strength": "500 mg",
                "pharmacy_rx_required": True,
                "pharmacy_approval_required": True,
                "available_in_pos": True,
                "pharmacy_active_ingredient_ids": [(6, 0, cls.ingredient.ids)],
                "pharmacy_register_type_ids": [
                    (6, 0, [cls.env.ref("noels_pharmacy.register_type_antibiotic").id])
                ],
            }
        )
        cls.product = cls.product_template.product_variant_id

    def _create_prescription(self):
        return self.env["pharmacy.prescription"].create(
            {
                "patient_id": self.patient.id,
                "purchaser_partner_id": self.partner.id,
                "prescriber_id": self.prescriber.id,
                "refills_allowed": 1,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "prescribed_qty": 21,
                            "product_uom_id": self.product.uom_id.id,
                            "dispensing_instructions": "Take one capsule three times daily for 7 days",
                        },
                    )
                ],
            }
        )

    def test_prescription_dispensing_and_register(self):
        prescription = self._create_prescription()
        self.assertTrue(prescription.name.startswith("TMP-"))
        prescription.action_submit()
        self.assertEqual(prescription.state, "awaiting_review")
        prescription.action_approve()
        self.assertEqual(prescription.state, "approved")

        dispensing = self.env["pharmacy.dispensing"].create(
            {
                "prescription_id": prescription.id,
                "pharmacist_id": self.staff.id,
                "source_reference": "POS/1002",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "prescription_line_id": prescription.line_ids.id,
                            "product_id": self.product.id,
                            "quantity": 21,
                            "product_uom_id": self.product.uom_id.id,
                            "dispensing_instructions": prescription.line_ids.dispensing_instructions,
                        },
                    )
                ],
            }
        )
        dispensing.action_confirm()

        self.assertEqual(dispensing.state, "confirmed")
        self.assertTrue(prescription.name.startswith("RX"))
        self.assertEqual(prescription.state, "partially_dispensed")
        self.assertEqual(prescription.line_ids.remaining_qty, 21)
        entry = self.env["pharmacy.register.entry"].search(
            [("dispensing_id", "=", dispensing.id)]
        )
        self.assertEqual(len(entry), 1)
        self.assertEqual(entry.quantity_out, 21)

    def test_allergy_alert_blocks_approval(self):
        self.patient.write({"allergy_status": "known"})
        self.env["pharmacy.patient.allergy"].create(
            {
                "patient_id": self.patient.id,
                "ingredient_id": self.ingredient.id,
                "allergen_name": self.ingredient.name,
                "severity": "severe",
            }
        )
        prescription = self._create_prescription()
        prescription.action_submit()
        blocking = prescription.clinical_alert_ids.filtered(
            lambda alert: alert.alert_type == "allergy" and alert.severity == "blocking"
        )
        self.assertTrue(blocking)
        with self.assertRaises(UserError):
            prescription.action_approve()

    def test_confirmed_dispensing_cannot_be_deleted(self):
        prescription = self._create_prescription()
        prescription.action_submit()
        prescription.action_approve()
        dispensing = self.env["pharmacy.dispensing"].create(
            {
                "prescription_id": prescription.id,
                "pharmacist_id": self.staff.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "prescription_line_id": prescription.line_ids.id,
                            "product_id": self.product.id,
                            "quantity": 21,
                            "product_uom_id": self.product.uom_id.id,
                            "dispensing_instructions": prescription.line_ids.dispensing_instructions,
                        },
                    )
                ],
            }
        )
        dispensing.action_confirm()
        with self.assertRaises(UserError):
            dispensing.unlink()

    def test_backend_preparation_creates_fill_barcode(self):
        prescription = self._create_prescription()
        prescription.action_submit()
        prescription.action_approve()

        action = prescription.action_prepare_for_pos()
        dispensing = self.env["pharmacy.dispensing"].browse(action["res_id"])
        self.assertEqual(dispensing.state, "draft")
        self.assertEqual(dispensing.label_size, "3x2")
        dispensing.action_ready_for_pos()

        self.assertEqual(dispensing.state, "ready")
        self.assertTrue(prescription.name.startswith("RX"))
        self.assertTrue(dispensing.checkout_barcode.startswith("NPX"))
        self.assertEqual(len(dispensing.checkout_barcode), 15)
        self.assertEqual(dispensing.label_print_count, 1)
        self.assertEqual(dispensing.line_ids.quantity, 21)

        dispensing.action_return_to_preparation()
        self.assertEqual(dispensing.state, "draft")
        self.assertFalse(dispensing.checkout_barcode)
