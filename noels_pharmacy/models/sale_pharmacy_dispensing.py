from odoo import fields, models


class PharmacyDispensing(models.Model):
    _inherit = "pharmacy.dispensing"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        copy=False,
        ondelete="restrict",
        index=True,
    )
    stock_picking_id = fields.Many2one(
        "stock.picking",
        string="Delivered Transfer",
        copy=False,
        ondelete="restrict",
        index=True,
    )
