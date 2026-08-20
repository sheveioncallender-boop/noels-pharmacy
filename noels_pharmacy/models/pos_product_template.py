from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        return fields_list + [
            "is_pharmacy_item",
            "pharmacy_generic_name",
            "pharmacy_strength",
            "pharmacy_rx_required",
            "pharmacy_approval_required",
            "pharmacy_default_route",
            "pharmacy_default_directions",
            "pharmacy_default_caution",
        ]
