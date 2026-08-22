import base64
import binascii

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.float_utils import float_compare


class PharmacyPrescription(models.Model):
    _inherit = "pharmacy.prescription"

    pos_order_uuid = fields.Char(copy=False, index=True, readonly=True)
    pos_order_id = fields.Many2one(
        "pos.order", string="POS Order", copy=False, readonly=True, ondelete="restrict", index=True
    )
    pos_pharmacist_id = fields.Many2one(
        "pharmacy.staff.profile", string="POS Pharmacist", copy=False, ondelete="restrict"
    )

    _pos_order_uuid_unique = models.Constraint(
        "unique(pos_order_uuid)", "A POS order can only be linked to one prescription."
    )

    @api.model
    def _check_pos_rpc_access(self):
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Only an authorised Point of Sale user can use prescription capture."))

    @api.model
    def _pos_patient(self, payload):
        Patient = self.env["pharmacy.patient"].sudo().with_company(self.env.company)
        Partner = self.env["res.partner"].sudo().with_company(self.env.company)
        partner_id = int(payload.get("partner_id") or 0)
        purchaser_partner_id = int(payload.get("purchaser_partner_id") or 0)
        partner = Partner.browse(partner_id).exists() if partner_id else Partner
        if not partner:
            patient_name = (payload.get("patient_name") or "").strip()
            if not patient_name:
                raise ValidationError(_("Select a customer or enter the walk-in patient's name."))
            partner = Partner.create({"name": patient_name, "customer_rank": 1})
        allergy_status = payload.get("allergy_status")
        if allergy_status not in ("unknown", "none", "known"):
            allergy_status = "unknown"
        patient = Patient.search(
            [("partner_id", "=", partner.id), ("company_id", "=", self.env.company.id)], limit=1
        )
        date_of_birth = payload.get("date_of_birth") or False
        if not patient:
            patient = Patient.create(
                {
                    "partner_id": partner.id,
                    "company_id": self.env.company.id,
                    "date_of_birth": date_of_birth,
                    "allergy_status": allergy_status,
                }
            )
        elif date_of_birth and not patient.date_of_birth:
            patient.write({"date_of_birth": date_of_birth})
        if patient.allergy_status == "unknown" and allergy_status != "unknown":
            patient.write({"allergy_status": allergy_status})
        allergy_name = (payload.get("allergy_name") or "").strip()
        if allergy_status == "known" and allergy_name:
            existing_allergy = patient.allergy_ids.filtered(
                lambda allergy: allergy.active
                and allergy.allergen_name.strip().casefold() == allergy_name.casefold()
            )
            if not existing_allergy:
                self.env["pharmacy.patient.allergy"].sudo().create(
                    {
                        "patient_id": patient.id,
                        "allergen_name": allergy_name,
                        "severity": "moderate",
                    }
                )
        purchaser = Partner.browse(purchaser_partner_id).exists() if purchaser_partner_id else partner
        return patient, purchaser

    @api.model
    def _pos_prescriber(self, payload):
        doctor_name = (payload.get("doctor_name") or "").strip()
        if not doctor_name:
            return self.env["pharmacy.prescriber"]
        licence = (payload.get("doctor_license") or "").strip()
        Prescriber = self.env["pharmacy.prescriber"].sudo().with_company(self.env.company)
        domain = [("company_id", "=", self.env.company.id)]
        domain.append(("license_number", "=", licence) if licence else ("name", "=ilike", doctor_name))
        prescriber = Prescriber.search(domain, limit=1)
        if not prescriber:
            partner = self.env["res.partner"].sudo().create({"name": doctor_name})
            prescriber = Prescriber.create(
                {
                    "partner_id": partner.id,
                    "license_number": licence or False,
                    "company_id": self.env.company.id,
                }
            )
        return prescriber

    @api.model
    def _pos_attachment(self, prescription, attachment):
        if not attachment or not attachment.get("data"):
            return
        mimetype = attachment.get("mimetype") or "application/octet-stream"
        if mimetype not in {"application/pdf", "image/jpeg", "image/png", "image/webp"}:
            raise ValidationError(_("Use a PDF, JPG, PNG, or WebP prescription file."))
        encoded = attachment["data"]
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValidationError(_("The uploaded prescription file is not valid.")) from error
        if len(raw) > 10 * 1024 * 1024:
            raise ValidationError(_("Prescription uploads are limited to 10 MB per file."))
        record = self.env["ir.attachment"].sudo().create(
            {
                "name": (attachment.get("name") or "prescription-upload")[:255],
                "type": "binary",
                "datas": encoded,
                "mimetype": mimetype,
                "res_model": prescription._name,
                "res_id": prescription.id,
            }
        )
        prescription.sudo().write({"attachment_ids": [fields.Command.link(record.id)]})

    @api.model
    def pos_get_prescription_status(self, order_uuid):
        self._check_pos_rpc_access()
        prescription = self.sudo().search([("pos_order_uuid", "=", order_uuid)], limit=1)
        if not prescription:
            return {"exists": False, "state": False, "label": _("Add Prescription")}
        return {
            "exists": True,
            "id": prescription.id,
            "reference": prescription.name,
            "state": prescription.state,
            "alert_count": prescription.alert_count,
            "label": _("Prescription Added"),
            "patient_name": prescription.patient_id.name,
            "patient_partner_id": prescription.patient_id.partner_id.id,
            "patient_is_customer": (
                prescription.patient_id.partner_id == prescription.purchaser_partner_id
            ),
        }

    @api.model
    def pos_save_prescription(self, payload):
        self._check_pos_rpc_access()
        order_uuid = (payload.get("order_uuid") or "").strip()
        if not order_uuid:
            raise ValidationError(_("The POS order identifier is missing."))
        existing = self.sudo().search([("pos_order_uuid", "=", order_uuid)], limit=1)
        if existing and existing.state != "draft":
            if existing.state == "awaiting_review" and payload.get("approve_now"):
                current_staff = existing.with_user(self.env.user)._current_staff_profile()
                if not current_staff or current_staff.role not in ("pharmacist", "manager"):
                    raise ValidationError(_("The logged-in user is not an active pharmacist or pharmacy manager."))
                if existing.pos_pharmacist_id and existing.pos_pharmacist_id != current_staff:
                    raise ValidationError(
                        _("The entered pharmacist initials do not belong to the logged-in pharmacist.")
                    )
                existing.with_user(self.env.user).action_approve()
            return self.pos_get_prescription_status(order_uuid)

        patient, purchaser = self._pos_patient(payload)
        prescriber = self._pos_prescriber(payload)
        Staff = self.env["pharmacy.staff.profile"].sudo().with_company(self.env.company)
        pharmacist_initials = (payload.get("pharmacist_initials") or "").strip()
        pharmacist = Staff.search(
            [
                ("initials", "=ilike", pharmacist_initials),
                ("company_id", "=", self.env.company.id),
                ("active", "=", True),
                ("role", "in", ("pharmacist", "manager")),
            ], limit=1
        ) if pharmacist_initials else Staff
        if pharmacist_initials and not pharmacist:
            raise ValidationError(
                _("No active pharmacist or pharmacy manager has the initials %s.")
                % pharmacist_initials
            )

        line_commands = []
        regulated = False
        Products = self.env["product.product"].sudo()
        for item in payload.get("lines") or []:
            product = Products.browse(int(item.get("product_id") or 0)).exists()
            if not product or not product.product_tmpl_id.is_pharmacy_item:
                continue
            quantity = float(item.get("quantity") or 0)
            if quantity <= 0:
                continue
            template = product.product_tmpl_id
            regulated = regulated or template.pharmacy_rx_required
            directions = (item.get("directions") or template.pharmacy_default_directions or "").strip()
            if not directions:
                raise ValidationError(_("Enter dispensing instructions for %s.") % product.display_name)
            line_commands.append(
                fields.Command.create(
                    {
                        "product_id": product.id,
                        "prescribed_qty": quantity,
                        "product_uom_id": product.uom_id.id,
                        "route": template.pharmacy_default_route,
                        "dispensing_instructions": directions,
                        "caution_instructions": template.pharmacy_default_caution,
                    }
                )
            )
        if not line_commands:
            raise ValidationError(_("The POS cart does not contain a pharmacy medicine."))
        if regulated and not prescriber:
            raise ValidationError(_("Enter the doctor/prescriber for prescription medicines."))

        values = {
            "patient_id": patient.id,
            "purchaser_partner_id": purchaser.id,
            "prescriber_id": prescriber.id or False,
            "prescription_date": payload.get("prescription_date") or fields.Date.context_today(self),
            "diagnosis_notes": (payload.get("diagnosis_notes") or "").strip(),
            "refills_allowed": max(int(payload.get("refills_allowed") or 0), 0),
            "source_type": payload.get("source_type") or "physical",
            "pos_order_uuid": order_uuid,
            "pos_pharmacist_id": pharmacist.id or False,
            "company_id": self.env.company.id,
            "line_ids": line_commands,
        }
        Prescription = self.sudo().with_company(self.env.company)
        if existing:
            existing.line_ids.unlink()
            existing.write(values)
            prescription = existing
        else:
            prescription = Prescription.create(values)
        self._pos_attachment(prescription, payload.get("attachment"))
        prescription.action_submit()

        current_staff = Staff.search(
            [
                ("user_id", "=", self.env.user.id),
                ("company_id", "=", self.env.company.id),
                ("active", "=", True),
                ("role", "in", ("pharmacist", "manager")),
            ], limit=1
        )
        if payload.get("approve_now") and current_staff and (not pharmacist or pharmacist == current_staff):
            prescription.with_user(self.env.user).action_approve()
        result = self.pos_get_prescription_status(order_uuid)
        result["approval_required"] = regulated
        return result

    @api.model
    def pos_validate_for_payment(self, order_uuid, lines):
        self._check_pos_rpc_access()
        prepared_result = self.env["pharmacy.dispensing"].pos_validate_checkout(order_uuid, lines)
        if prepared_result.get("prepared") or not prepared_result.get("ok"):
            return prepared_result
        product_ids = [int(item.get("product_id") or 0) for item in (lines or [])]
        products = self.env["product.product"].sudo().browse(product_ids).exists()
        regulated = products.filtered(
            lambda product: product.product_tmpl_id.pharmacy_rx_required
            or product.product_tmpl_id.pharmacy_approval_required
        )
        if not regulated:
            return {"ok": True}
        prescription = self.sudo().search([("pos_order_uuid", "=", order_uuid)], limit=1)
        if not prescription:
            return {
                "ok": False,
                "message": _(
                    "This order contains regulated medicine. Prepare the prescription in the Pharmacy app, then scan its checkout barcode."
                ),
            }
        if prescription.state not in ("approved", "partially_dispensed"):
            return {"ok": False, "message": _("The prescription is awaiting pharmacist approval. Payment has not been processed.")}
        prescribed_ids = set(prescription.line_ids.product_id.ids)
        missing = regulated.filtered(lambda product: product.id not in prescribed_ids)
        if missing:
            return {"ok": False, "message": _("The approved prescription does not cover: %s") % ", ".join(missing.mapped("display_name"))}
        requested_qty = {}
        for item in lines or []:
            product_id = int(item.get("product_id") or 0)
            requested_qty[product_id] = requested_qty.get(product_id, 0.0) + float(
                item.get("quantity") or 0
            )
        for product in regulated:
            available_qty = sum(
                prescription.line_ids.filtered(
                    lambda line: line.product_id == product
                ).mapped("remaining_qty")
            )
            if float_compare(
                available_qty,
                requested_qty.get(product.id, 0.0),
                precision_rounding=product.uom_id.rounding,
            ) < 0:
                return {
                    "ok": False,
                    "message": _("The approved prescription quantity is insufficient for %s.")
                    % product.display_name,
                }
        return {"ok": True, "prescription_id": prescription.id}
