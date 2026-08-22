from odoo import fields, models


class PharmacyRegisterType(models.Model):
    _name = "pharmacy.register.type"
    _description = "Pharmacy Register Type"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _code_company_unique = models.Constraint(
        "unique(code, company_id)",
        "The register code must be unique per company.",
    )


class PharmacyTherapeuticClass(models.Model):
    _name = "pharmacy.therapeutic.class"
    _description = "Therapeutic Class"
    _order = "name"

    name = fields.Char(required=True, index=True)
    code = fields.Char(index=True)
    active = fields.Boolean(default=True)


class PharmacyActiveIngredient(models.Model):
    _name = "pharmacy.active.ingredient"
    _description = "Active Ingredient"
    _order = "name"

    name = fields.Char(required=True, index=True)
    code = fields.Char(index=True)
    therapeutic_class_id = fields.Many2one("pharmacy.therapeutic.class", index=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _ingredient_name_unique = models.Constraint(
        "unique(name)",
        "The active ingredient already exists.",
    )
