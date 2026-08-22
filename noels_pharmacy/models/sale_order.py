from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    pharmacy_prescription_id = fields.Many2one(
        "pharmacy.prescription",
        string="Prescription",
        copy=False,
        ondelete="restrict",
        tracking=True,
    )
    pharmacy_patient_id = fields.Many2one(
        related="pharmacy_prescription_id.patient_id",
        string="Patient",
        store=True,
    )
    pharmacy_requires_prescription = fields.Boolean(
        compute="_compute_pharmacy_requirements",
        store=True,
    )
    pharmacy_requires_approval = fields.Boolean(
        compute="_compute_pharmacy_requirements",
        store=True,
    )
    pharmacy_dispensing_count = fields.Integer(compute="_compute_pharmacy_dispensing_count")

    @api.depends(
        "order_line.product_id",
        "order_line.product_id.product_tmpl_id.pharmacy_rx_required",
        "order_line.product_id.product_tmpl_id.pharmacy_approval_required",
    )
    def _compute_pharmacy_requirements(self):
        for order in self:
            templates = order.order_line.product_id.product_tmpl_id
            order.pharmacy_requires_prescription = any(templates.mapped("pharmacy_rx_required"))
            order.pharmacy_requires_approval = any(templates.mapped("pharmacy_approval_required"))

    def _compute_pharmacy_dispensing_count(self):
        grouped = self.env["pharmacy.dispensing"]._read_group(
            [("sale_order_id", "in", self.ids)],
            ["sale_order_id"],
            ["__count"],
        )
        counts = {order.id: count for order, count in grouped}
        for order in self:
            order.pharmacy_dispensing_count = counts.get(order.id, 0)

    def _pharmacy_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type
            and line.product_id.product_tmpl_id.is_pharmacy_item
            and line.product_uom_qty > 0
        )

    def action_create_pharmacy_prescription(self):
        self.ensure_one()
        if self.pharmacy_prescription_id:
            return self.action_view_pharmacy_prescription()
        pharmacy_lines = self._pharmacy_lines()
        if not pharmacy_lines:
            raise UserError(_("This quotation does not contain any products marked as pharmacy medicines."))
        patient = self.env["pharmacy.patient"].search(
            [
                ("partner_id", "=", self.partner_id.id),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not patient:
            patient = self.env["pharmacy.patient"].create(
                {
                    "partner_id": self.partner_id.id,
                    "company_id": self.company_id.id,
                    "allergy_status": "unknown",
                }
            )
        commands = []
        for sale_line in pharmacy_lines:
            template = sale_line.product_id.product_tmpl_id
            directions = (
                sale_line.pharmacy_dispensing_instructions
                or template.pharmacy_default_directions
                or _("Directions to be confirmed")
            )
            commands.append(
                fields.Command.create(
                    {
                        "product_id": sale_line.product_id.id,
                        "prescribed_qty": sale_line.product_uom_qty,
                        "product_uom_id": sale_line.product_uom_id.id,
                        "route": template.pharmacy_default_route,
                        "dispensing_instructions": directions,
                        "directions_pending": not bool(sale_line.pharmacy_dispensing_instructions),
                        "caution_instructions": template.pharmacy_default_caution,
                    }
                )
            )
        prescription = self.env["pharmacy.prescription"].create(
            {
                "patient_id": patient.id,
                "purchaser_partner_id": self.partner_id.id,
                "prescription_date": fields.Date.context_today(self),
                "source_type": "other",
                "external_reference": self.name,
                "company_id": self.company_id.id,
                "line_ids": commands,
            }
        )
        self.pharmacy_prescription_id = prescription
        pharmacy_lines._link_prescription_lines(prescription)
        return self.action_view_pharmacy_prescription()

    def action_view_pharmacy_prescription(self):
        self.ensure_one()
        if not self.pharmacy_prescription_id:
            return self.action_create_pharmacy_prescription()
        return {
            "type": "ir.actions.act_window",
            "name": _("Prescription"),
            "res_model": "pharmacy.prescription",
            "view_mode": "form",
            "res_id": self.pharmacy_prescription_id.id,
        }

    def action_view_pharmacy_dispensing(self):
        self.ensure_one()
        action = self.env.ref("noels_pharmacy.action_pharmacy_dispensing").read()[0]
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {
            "default_sale_order_id": self.id,
            "default_prescription_id": self.pharmacy_prescription_id.id,
            "default_source_type": "sale",
            "default_source_reference": self.name,
        }
        return action

    def action_print_pharmacy_labels(self):
        self.ensure_one()
        if not self.pharmacy_prescription_id:
            raise UserError(_("No prescription is linked to this order."))
        return self.pharmacy_prescription_id.action_print_labels()

    def action_create_pharmacy_dispensing(self):
        self.ensure_one()
        prescription = self.pharmacy_prescription_id
        if not prescription:
            raise UserError(_("Create and review the prescription first."))
        if prescription.state not in ("approved", "partially_dispensed"):
            raise UserError(_("The prescription must be pharmacist-approved before dispensing."))
        dispensing = self.env["pharmacy.dispensing"].create(
            {
                "prescription_id": prescription.id,
                "sale_order_id": self.id,
                "source_type": "sale",
                "source_reference": self.name,
                "stock_picking_id": self.picking_ids.filtered(
                    lambda picking: picking.state == "done"
                )[:1].id,
            }
        )
        dispensing._onchange_prescription_id()
        return {
            "type": "ir.actions.act_window",
            "name": _("Dispensing"),
            "res_model": "pharmacy.dispensing",
            "view_mode": "form",
            "res_id": dispensing.id,
        }

    def action_confirm(self):
        for order in self:
            if not (order.pharmacy_requires_prescription or order.pharmacy_requires_approval):
                continue
            prescription = order.pharmacy_prescription_id
            if not prescription:
                raise UserError(
                    _("Add a prescription before confirming this order because it contains prescription medicines.")
                )
            if prescription.state not in ("approved", "partially_dispensed"):
                raise UserError(_("The linked prescription must be pharmacist-approved before confirmation."))
            if (
                prescription.purchaser_partner_id.commercial_partner_id
                != order.partner_id.commercial_partner_id
            ):
                raise UserError(_("The linked prescription belongs to a different customer/purchaser."))
            regulated_lines = order.order_line.filtered(
                lambda line: not line.display_type
                and (
                    line.product_id.product_tmpl_id.pharmacy_rx_required
                    or line.product_id.product_tmpl_id.pharmacy_approval_required
                )
                and line.product_uom_qty > 0
            )
            for product in regulated_lines.product_id:
                prescription_lines = prescription.line_ids.filtered(
                    lambda line: line.product_id == product
                )
                sale_qty = sum(
                    sale_line.product_uom_id._compute_quantity(
                        sale_line.product_uom_qty, product.uom_id
                    )
                    for sale_line in regulated_lines.filtered(
                        lambda line: line.product_id == product
                    )
                )
                available_qty = sum(
                    line.product_uom_id._compute_quantity(
                        line.remaining_qty, product.uom_id
                    )
                    for line in prescription_lines
                )
                if not prescription_lines or float_compare(
                    available_qty,
                    sale_qty,
                    precision_rounding=product.uom_id.rounding,
                ) < 0:
                    raise UserError(
                        _("The approved prescription does not cover the ordered quantity of %s.")
                        % product.display_name
                    )
        return super().action_confirm()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    pharmacy_prescription_line_id = fields.Many2one(
        "pharmacy.prescription.line",
        string="Prescription Medicine Line",
        copy=False,
        ondelete="set null",
    )
    pharmacy_dispensing_instructions = fields.Text(
        string="Dispensing Instructions",
        help="Example: Take one tablet by mouth once daily after food.",
    )

    @api.onchange("product_id")
    def _onchange_pharmacy_product_id(self):
        if self.product_id.product_tmpl_id.is_pharmacy_item:
            self.pharmacy_dispensing_instructions = (
                self.product_id.product_tmpl_id.pharmacy_default_directions
            )

    def _link_prescription_lines(self, prescription):
        available = prescription.line_ids
        for line in self:
            match = available.filtered(lambda item: item.product_id == line.product_id)[:1]
            if match:
                line.pharmacy_prescription_line_id = match
                available -= match
