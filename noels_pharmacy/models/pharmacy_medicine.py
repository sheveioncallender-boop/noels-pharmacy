from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_pharmacy_item = fields.Boolean(string="Pharmacy Medicine", index=True)
    pharmacy_generic_name = fields.Char(string="Generic Name", index=True)
    pharmacy_strength = fields.Char(string="Strength")
    pharmacy_dosage_form = fields.Selection(
        [
            ("tablet", "Tablet"),
            ("capsule", "Capsule"),
            ("liquid", "Oral Liquid"),
            ("cream", "Cream"),
            ("ointment", "Ointment"),
            ("drops", "Drops"),
            ("inhaler", "Inhaler"),
            ("injection", "Injection"),
            ("suppository", "Suppository"),
            ("other", "Other"),
        ],
        string="Dosage Form",
    )
    pharmacy_default_route = fields.Selection(
        [
            ("oral", "Oral"),
            ("topical", "Topical"),
            ("inhaled", "Inhaled"),
            ("ophthalmic", "Ophthalmic"),
            ("otic", "Otic"),
            ("nasal", "Nasal"),
            ("rectal", "Rectal"),
            ("vaginal", "Vaginal"),
            ("injection", "Injection"),
            ("other", "Other"),
        ],
        string="Default Route",
    )
    pharmacy_registration_number = fields.Char(string="Drug Registration Number", index=True)
    pharmacy_manufacturer = fields.Char(string="Manufacturer")
    pharmacy_storage_instructions = fields.Char(string="Storage Instructions")
    pharmacy_default_directions = fields.Text(string="Default Dispensing Directions")
    pharmacy_default_caution = fields.Text(string="Default Caution")
    pharmacy_rx_required = fields.Boolean(string="Prescription Required")
    pharmacy_approval_required = fields.Boolean(string="Pharmacist Approval Required")
    pharmacy_substitution_allowed = fields.Boolean(string="Generic Substitution Allowed", default=True)
    pharmacy_active_ingredient_ids = fields.Many2many(
        "pharmacy.active.ingredient",
        "pharmacy_product_ingredient_rel",
        "product_tmpl_id",
        "ingredient_id",
        string="Active Ingredients",
    )
    pharmacy_therapeutic_class_id = fields.Many2one(
        "pharmacy.therapeutic.class",
        string="Therapeutic Class",
        index=True,
    )
    pharmacy_register_type_ids = fields.Many2many(
        "pharmacy.register.type",
        "pharmacy_product_register_rel",
        "product_tmpl_id",
        "register_type_id",
        string="Regulatory Registers",
    )

    @api.onchange("pharmacy_register_type_ids")
    def _onchange_pharmacy_register_types(self):
        if self.pharmacy_register_type_ids:
            self.is_pharmacy_item = True
            self.pharmacy_rx_required = True
            self.pharmacy_approval_required = True

