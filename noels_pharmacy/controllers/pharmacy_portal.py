import base64

from werkzeug.exceptions import NotFound

from odoo import fields, http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PharmacyWebsiteController(http.Controller):
    def _patient_domain(self):
        partner = request.env.user.partner_id
        return [
            ("partner_id", "=", partner.id),
            ("company_id", "=", request.env.company.id),
        ]

    def _owned_prescription(self, prescription_id):
        patient_ids = request.env["pharmacy.patient"].sudo().search(self._patient_domain()).ids
        prescription = request.env["pharmacy.prescription"].sudo().search(
            [("id", "=", prescription_id), ("patient_id", "in", patient_ids)], limit=1
        )
        if not prescription:
            raise NotFound()
        return prescription

    @http.route("/pharmacy/prescription/upload", type="http", auth="user", website=True, methods=["GET"])
    def prescription_upload(self, **kwargs):
        order = request.cart
        if not order:
            return request.redirect("/shop/cart")
        pharmacy_lines = order.order_line.filtered(
            lambda line: not line.display_type and line.product_id.product_tmpl_id.is_pharmacy_item
        )
        if not pharmacy_lines:
            return request.redirect("/shop/cart")
        return request.render(
            "noels_pharmacy.prescription_upload_page",
            {"order": order, "pharmacy_lines": pharmacy_lines, "error": kwargs.get("error")},
        )

    @http.route("/pharmacy/prescription/upload/submit", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def prescription_upload_submit(self, **post):
        order = request.cart
        if not order or order.partner_id.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            raise NotFound()
        upload = request.httprequest.files.get("prescription_file")
        if not upload or not upload.filename:
            return request.redirect("/pharmacy/prescription/upload?error=file")
        allowed_types = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
        if upload.mimetype not in allowed_types:
            return request.redirect("/pharmacy/prescription/upload?error=type")
        content = upload.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            return request.redirect("/pharmacy/prescription/upload?error=size")

        partner = order.partner_id
        Patient = request.env["pharmacy.patient"].sudo().with_company(order.company_id)
        allergy_status = post.get("allergy_status")
        if allergy_status not in ("unknown", "none", "known"):
            allergy_status = "unknown"
        patient = Patient.search(
            [("partner_id", "=", partner.id), ("company_id", "=", order.company_id.id)], limit=1
        )
        if not patient:
            patient = Patient.create(
                {
                    "partner_id": partner.id,
                    "company_id": order.company_id.id,
                    "date_of_birth": post.get("date_of_birth") or False,
                    "allergy_status": allergy_status,
                }
            )
        elif post.get("date_of_birth") and not patient.date_of_birth:
            patient.write({"date_of_birth": post["date_of_birth"]})
        if patient.allergy_status == "unknown" and allergy_status != "unknown":
            patient.write({"allergy_status": allergy_status})
        allergy_name = (post.get("allergy_name") or "").strip()
        if allergy_status == "known" and allergy_name:
            existing_allergy = patient.allergy_ids.filtered(
                lambda allergy: allergy.active
                and allergy.allergen_name.strip().casefold() == allergy_name.casefold()
            )
            if not existing_allergy:
                request.env["pharmacy.patient.allergy"].sudo().create(
                    {"patient_id": patient.id, "allergen_name": allergy_name, "severity": "moderate"}
                )

        doctor_name = (post.get("doctor_name") or "").strip()
        doctor_license = (post.get("doctor_license") or "").strip()
        prescriber = request.env["pharmacy.prescriber"].sudo()
        if doctor_name:
            domain = [("company_id", "=", order.company_id.id)]
            domain.append(("license_number", "=", doctor_license) if doctor_license else ("name", "=ilike", doctor_name))
            prescriber = prescriber.search(domain, limit=1)
            if not prescriber:
                doctor_partner = request.env["res.partner"].sudo().create({"name": doctor_name})
                prescriber = request.env["pharmacy.prescriber"].sudo().create(
                    {
                        "partner_id": doctor_partner.id,
                        "license_number": doctor_license or False,
                        "company_id": order.company_id.id,
                    }
                )

        commands = []
        pharmacy_lines = order.order_line.filtered(
            lambda line: not line.display_type
            and line.product_id.product_tmpl_id.is_pharmacy_item
            and line.product_uom_qty > 0
        )
        for line in pharmacy_lines:
            template = line.product_id.product_tmpl_id
            commands.append(
                fields.Command.create(
                    {
                        "product_id": line.product_id.id,
                        "prescribed_qty": line.product_uom_qty,
                        "product_uom_id": line.product_uom_id.id,
                        "route": template.pharmacy_default_route,
                        "dispensing_instructions": template.pharmacy_default_directions or _("As directed on uploaded prescription"),
                        "directions_pending": True,
                        "caution_instructions": template.pharmacy_default_caution,
                    }
                )
            )
        prescription = request.env["pharmacy.prescription"].sudo().create(
            {
                "patient_id": patient.id,
                "purchaser_partner_id": partner.id,
                "prescriber_id": prescriber.id or False,
                "prescription_date": post.get("prescription_date") or fields.Date.context_today(patient),
                "diagnosis_notes": (post.get("diagnosis_notes") or "").strip(),
                "refills_allowed": max(int(post.get("refills_allowed") or 0), 0),
                "source_type": "website",
                "external_reference": order.name,
                "company_id": order.company_id.id,
                "line_ids": commands,
            }
        )
        attachment = request.env["ir.attachment"].sudo().create(
            {
                "name": upload.filename[:255],
                "type": "binary",
                "datas": base64.b64encode(content),
                "mimetype": upload.mimetype,
                "res_model": prescription._name,
                "res_id": prescription.id,
            }
        )
        prescription.write({"attachment_ids": [fields.Command.link(attachment.id)]})
        order.sudo().write({"pharmacy_prescription_id": prescription.id})
        order.order_line.sudo()._link_prescription_lines(prescription)
        return request.redirect("/shop/cart?prescription_uploaded=1")

    @http.route(["/my/prescriptions", "/my/prescriptions/page/<int:page>"], type="http", auth="user", website=True)
    def portal_prescriptions(self, page=1, **kwargs):
        patient_ids = request.env["pharmacy.patient"].sudo().search(self._patient_domain()).ids
        domain = [("patient_id", "in", patient_ids)]
        Prescription = request.env["pharmacy.prescription"].sudo()
        total = Prescription.search_count(domain)
        page_size = 20
        pager = portal_pager(
            url="/my/prescriptions", total=total, page=page, step=page_size
        )
        prescriptions = Prescription.search(
            domain,
            order="prescription_date desc, id desc",
            limit=page_size,
            offset=pager["offset"],
        )
        return request.render(
            "noels_pharmacy.portal_my_prescriptions",
            {"prescriptions": prescriptions, "pager": pager, "page_name": "prescriptions"},
        )

    @http.route("/my/prescriptions/<int:prescription_id>", type="http", auth="user", website=True)
    def portal_prescription_detail(self, prescription_id, **kwargs):
        prescription = self._owned_prescription(prescription_id)
        return request.render(
            "noels_pharmacy.portal_prescription_detail",
            {"prescription": prescription, "page_name": "prescriptions"},
        )
