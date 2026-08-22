import base64
import logging

from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    pharmacy_prescription_id = fields.Many2one(
        "pharmacy.prescription", string="Prescription", copy=False, ondelete="restrict", index=True
    )
    pharmacy_dispensing_ids = fields.One2many(
        "pharmacy.dispensing", "pos_order_id", string="Dispensing Records"
    )
    pharmacy_dispensing_count = fields.Integer(compute="_compute_pharmacy_dispensing_count")

    def _compute_pharmacy_dispensing_count(self):
        for order in self:
            order.pharmacy_dispensing_count = len(order.pharmacy_dispensing_ids)

    def _process_saved_order(self, draft):
        result = super()._process_saved_order(draft)
        if not draft and self.state != "cancel":
            self._pharmacy_process_paid_order()
        return result

    def _pharmacy_process_paid_order(self):
        for order in self:
            prepared = self.env["pharmacy.dispensing"].sudo().search(
                [
                    ("checkout_order_uuid", "=", order.uuid),
                    ("company_id", "=", order.company_id.id),
                ],
                limit=1,
            )
            if prepared:
                if prepared.pos_order_id and prepared.pos_order_id != order:
                    raise ValidationError(_("This prepared prescription is already linked to another POS order."))
                order.pharmacy_prescription_id = prepared.prescription_id
                prepared.write(
                    {
                        "pos_order_id": order.id,
                        "source_type": "pos",
                        "source_reference": order.pos_reference or order.name,
                    }
                )
                if prepared.state == "ready":
                    prepared.action_confirm()
                elif prepared.state != "confirmed":
                    order.message_post(
                        body=_("The linked prescription fill requires pharmacy review before it can be confirmed.")
                    )
                continue

            # Backward-compatible processing for prescriptions captured in older
            # releases directly from the POS popup.
            prescription = self.env["pharmacy.prescription"].sudo().search(
                [("pos_order_uuid", "=", order.uuid), ("company_id", "=", order.company_id.id)], limit=1
            )
            if not prescription:
                continue
            if prescription.pos_order_id and prescription.pos_order_id != order:
                raise ValidationError(_("This prescription is already linked to another POS order."))
            prescription.write({"pos_order_id": order.id})
            order.pharmacy_prescription_id = prescription
            if order.pharmacy_dispensing_ids or prescription.state not in ("approved", "partially_dispensed"):
                continue
            pharmacist = prescription.pos_pharmacist_id or prescription.approved_by_id
            if not pharmacist:
                order.message_post(body=_("Prescription linked; dispensing awaits pharmacist assignment."))
                continue
            commands = []
            for order_line in order.lines.filtered(lambda line: line.qty > 0):
                prescription_line = prescription.line_ids.filtered(
                    lambda line: line.product_id == order_line.product_id and line.remaining_qty > 0
                )[:1]
                if not prescription_line:
                    continue
                quantity = min(order_line.qty, prescription_line.remaining_qty)
                lot = self.env["stock.lot"]
                if order_line.product_id.tracking != "none" and order_line.pack_lot_ids:
                    lot_name = order_line.pack_lot_ids[0].lot_name
                    lot = self.env["stock.lot"].search(
                        [("name", "=", lot_name), ("product_id", "=", order_line.product_id.id), ("company_id", "in", [False, order.company_id.id])],
                        limit=1,
                    )
                commands.append(
                    fields.Command.create(
                        {
                            "prescription_line_id": prescription_line.id,
                            "product_id": order_line.product_id.id,
                            "quantity": quantity,
                            "product_uom_id": prescription_line.product_uom_id.id,
                            "lot_id": lot.id or False,
                            "dispensing_instructions": prescription_line.dispensing_instructions,
                        }
                    )
                )
            if not commands:
                continue
            dispensing = self.env["pharmacy.dispensing"].sudo().create(
                {
                    "prescription_id": prescription.id,
                    "pharmacist_id": pharmacist.id,
                    "pos_order_id": order.id,
                    "source_type": "pos",
                    "source_reference": order.pos_reference or order.name,
                    "line_ids": commands,
                }
            )
            try:
                dispensing.action_confirm()
            except (UserError, ValidationError) as error:
                _logger.info("POS dispensing %s remains in draft: %s", dispensing.name, error)
                order.message_post(body=_("Dispensing record %s was created in Draft and needs completion: %s") % (dispensing.name, error))

    def action_view_pharmacy_prescription(self):
        self.ensure_one()
        if not self.pharmacy_prescription_id:
            raise UserError(_("No prescription is linked to this POS order."))
        return {"type": "ir.actions.act_window", "name": _("Prescription"), "res_model": "pharmacy.prescription", "view_mode": "form", "res_id": self.pharmacy_prescription_id.id}

    def action_view_pharmacy_dispensing(self):
        self.ensure_one()
        action = self.env.ref("noels_pharmacy.action_pharmacy_dispensing").read()[0]
        action["domain"] = [("pos_order_id", "=", self.id)]
        return action

    def action_get_pharmacy_label_pdf(self):
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise UserError(_("Only an authorised POS user can print these labels."))
        dispensing = self.sudo().pharmacy_dispensing_ids.filtered(
            lambda record: record.checkout_barcode and record.state in ("ready", "confirmed")
        ).sorted("id", reverse=True)[:1]
        prescription = self.sudo().pharmacy_prescription_id
        if not prescription:
            raise UserError(_("No prescription is linked to this POS order."))
        if not dispensing:
            dispensing = prescription.dispensing_ids.filtered(
                lambda record: record.checkout_barcode and record.state in ("ready", "confirmed")
            ).sorted("id", reverse=True)[:1]
        if not dispensing:
            raise UserError(_("No barcode-ready dispensing record is linked to this POS order."))
        report_xmlid = dispensing._label_report_xmlid()
        dispensing._log_label_print(dispensing.label_size)
        pdf, _content_type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
            report_xmlid,
            res_ids=dispensing.line_ids.ids,
        )
        return {
            "filename": "Medication Labels - %s.pdf" % prescription.name,
            "data": base64.b64encode(pdf).decode(),
        }


class PharmacyDispensing(models.Model):
    _inherit = "pharmacy.dispensing"

    pos_order_id = fields.Many2one("pos.order", string="POS Order", copy=False, ondelete="restrict", index=True)
