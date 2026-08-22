from collections import Counter
from itertools import combinations

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PharmacyInteractionRule(models.Model):
    _name = "pharmacy.interaction.rule"
    _description = "Drug Interaction Rule"
    _inherit = ["pharmacy.audit.mixin"]
    _order = "severity desc, ingredient_a_id, ingredient_b_id"

    _pharmacy_audit_fields = (
        "ingredient_a_id",
        "ingredient_b_id",
        "severity",
        "title",
        "description",
        "recommended_action",
        "active",
    )

    ingredient_a_id = fields.Many2one("pharmacy.active.ingredient", required=True, ondelete="restrict")
    ingredient_b_id = fields.Many2one("pharmacy.active.ingredient", required=True, ondelete="restrict")
    severity = fields.Selection(
        [("information", "Information"), ("warning", "Warning"), ("blocking", "Blocking")],
        required=True,
        default="warning",
        index=True,
    )
    title = fields.Char(required=True)
    description = fields.Text(required=True)
    recommended_action = fields.Text()
    source_reference = fields.Char(string="Clinical Source / Reference")
    active = fields.Boolean(default=True)

    @api.constrains("ingredient_a_id", "ingredient_b_id")
    def _check_ingredients(self):
        for rule in self:
            if rule.ingredient_a_id == rule.ingredient_b_id:
                raise ValidationError(_("An interaction rule requires two different ingredients."))
            duplicate = self.search_count(
                [
                    ("id", "!=", rule.id),
                    ("active", "=", True),
                    "|",
                    "&",
                    ("ingredient_a_id", "=", rule.ingredient_a_id.id),
                    ("ingredient_b_id", "=", rule.ingredient_b_id.id),
                    "&",
                    ("ingredient_a_id", "=", rule.ingredient_b_id.id),
                    ("ingredient_b_id", "=", rule.ingredient_a_id.id),
                ]
            )
            if duplicate:
                raise ValidationError(_("An active rule already exists for this ingredient pair."))


class PharmacyClinicalAlert(models.Model):
    _name = "pharmacy.clinical.alert"
    _description = "Clinical Alert"
    _inherit = ["pharmacy.audit.mixin"]
    _order = "severity desc, create_date desc, id desc"

    _pharmacy_audit_fields = (
        "prescription_id",
        "alert_type",
        "severity",
        "title",
        "description",
        "status",
        "override_reason",
        "overridden_by_id",
        "overridden_at",
    )

    prescription_id = fields.Many2one(
        "pharmacy.prescription",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="prescription_id.company_id", store=True, index=True)
    patient_id = fields.Many2one(related="prescription_id.patient_id", store=True, index=True)
    alert_type = fields.Selection(
        [
            ("allergy", "Allergy"),
            ("interaction", "Drug Interaction"),
            ("duplicate", "Duplicate Therapy"),
            ("profile", "Patient Profile"),
        ],
        required=True,
        index=True,
    )
    severity = fields.Selection(
        [("information", "Information"), ("warning", "Warning"), ("blocking", "Blocking")],
        required=True,
        index=True,
    )
    title = fields.Char(required=True)
    description = fields.Text(required=True)
    product_ids = fields.Many2many("product.product", string="Related Medicines", readonly=True)
    status = fields.Selection(
        [
            ("open", "Open"),
            ("acknowledged", "Acknowledged"),
            ("overridden", "Overridden"),
            ("superseded", "Superseded by New Check"),
        ],
        required=True,
        default="open",
        index=True,
    )
    override_reason = fields.Text()
    overridden_by_id = fields.Many2one("pharmacy.staff.profile", readonly=True)
    overridden_at = fields.Datetime(readonly=True)

    def action_acknowledge(self):
        for alert in self:
            if alert.status != "open":
                continue
            alert.write({"status": "acknowledged"})
        return True

    def action_override(self):
        for alert in self:
            if alert.status not in ("open", "acknowledged"):
                raise UserError(_("Only active clinical alerts can be overridden."))
            if not alert.override_reason:
                raise UserError(_("Enter the clinical reason for the override."))
            staff = alert.prescription_id._current_staff_profile()
            if not staff or staff.role not in ("pharmacist", "manager"):
                raise UserError(_("Only an active pharmacist or pharmacy manager can override an alert."))
            alert.write(
                {
                    "status": "overridden",
                    "overridden_by_id": staff.id,
                    "overridden_at": fields.Datetime.now(),
                }
            )
        return True

    def unlink(self):
        raise UserError(_("Clinical alerts cannot be deleted."))


class PharmacyPrescriptionAlertEngine(models.Model):
    _inherit = "pharmacy.prescription"

    def _create_clinical_alert(self, values):
        self.ensure_one()
        values.update(
            {
                "prescription_id": self.id,
                "status": "open",
            }
        )
        return self.env["pharmacy.clinical.alert"].sudo().create(values)

    def action_run_clinical_checks(self):
        for prescription in self:
            prescription.clinical_alert_ids.filtered(
                lambda alert: alert.status in ("open", "acknowledged")
            ).sudo().write({"status": "superseded"})

            products = prescription.line_ids.mapped("product_id")
            active_history_lines = self.env["pharmacy.prescription.line"].search(
                [
                    ("prescription_id.patient_id", "=", prescription.patient_id.id),
                    ("prescription_id", "!=", prescription.id),
                    ("prescription_id.state", "in", ("approved", "partially_dispensed")),
                    ("remaining_qty", ">", 0),
                    "|",
                    ("prescription_id.valid_until", "=", False),
                    ("prescription_id.valid_until", ">=", fields.Date.context_today(prescription)),
                ]
            )
            therapy_products = products | active_history_lines.mapped("product_id")
            ingredients_by_product = {
                product.id: product.product_tmpl_id.pharmacy_active_ingredient_ids
                for product in therapy_products
            }
            all_ingredients = self.env["pharmacy.active.ingredient"]
            for ingredients in ingredients_by_product.values():
                all_ingredients |= ingredients

            if prescription.patient_id.allergy_status == "unknown":
                prescription._create_clinical_alert(
                    {
                        "alert_type": "profile",
                        "severity": "warning",
                        "title": _("Allergy status not confirmed"),
                        "description": _("Confirm the patient's allergy status before pharmacist approval."),
                        "product_ids": [(6, 0, products.ids)],
                    }
                )

            for allergy in prescription.patient_id.allergy_ids.filtered("active"):
                if allergy.ingredient_id and allergy.ingredient_id in all_ingredients:
                    related_products = products.filtered(
                        lambda product: allergy.ingredient_id
                        in product.product_tmpl_id.pharmacy_active_ingredient_ids
                    )
                    prescription._create_clinical_alert(
                        {
                            "alert_type": "allergy",
                            "severity": "blocking",
                            "title": _("Allergy conflict: %s") % allergy.allergen_name,
                            "description": allergy.reaction
                            or _("The prescribed medicine contains a recorded patient allergen."),
                            "product_ids": [(6, 0, related_products.ids)],
                        }
                    )
                elif not allergy.ingredient_id:
                    prescription._create_clinical_alert(
                        {
                            "alert_type": "allergy",
                            "severity": "warning",
                            "title": _("Review recorded allergy: %s") % allergy.allergen_name,
                            "description": _("This allergy is recorded as free text and requires pharmacist review."),
                            "product_ids": [(6, 0, products.ids)],
                        }
                    )

            ingredient_counts = Counter()
            for ingredients in ingredients_by_product.values():
                ingredient_counts.update(ingredients.ids)
            for ingredient_id, count in ingredient_counts.items():
                if count <= 1:
                    continue
                ingredient = self.env["pharmacy.active.ingredient"].browse(ingredient_id)
                related_products = therapy_products.filtered(
                    lambda product: ingredient in product.product_tmpl_id.pharmacy_active_ingredient_ids
                )
                if not (related_products & products):
                    continue
                prescription._create_clinical_alert(
                    {
                        "alert_type": "duplicate",
                        "severity": "warning",
                        "title": _("Duplicate active ingredient: %s") % ingredient.name,
                        "description": _("More than one prescribed product contains this active ingredient."),
                        "product_ids": [(6, 0, related_products.ids)],
                    }
                )

            therapeutic_counts = Counter(
                therapy_products.mapped("product_tmpl_id.pharmacy_therapeutic_class_id").ids
            )
            for therapeutic_id, count in therapeutic_counts.items():
                if count <= 1:
                    continue
                therapeutic = self.env["pharmacy.therapeutic.class"].browse(therapeutic_id)
                related_therapy_products = therapy_products.filtered(
                    lambda product: product.product_tmpl_id.pharmacy_therapeutic_class_id
                    == therapeutic
                )
                if not (related_therapy_products & products):
                    continue
                prescription._create_clinical_alert(
                    {
                        "alert_type": "duplicate",
                        "severity": "warning",
                        "title": _("Possible duplicate therapy: %s") % therapeutic.name,
                        "description": _("Multiple medicines belong to the same therapeutic class."),
                        "product_ids": [
                            (
                                6,
                                0,
                                related_therapy_products.ids,
                            )
                        ],
                    }
                )

            for ingredient_a_id, ingredient_b_id in combinations(sorted(set(all_ingredients.ids)), 2):
                rule = self.env["pharmacy.interaction.rule"].search(
                    [
                        ("active", "=", True),
                        "|",
                        "&",
                        ("ingredient_a_id", "=", ingredient_a_id),
                        ("ingredient_b_id", "=", ingredient_b_id),
                        "&",
                        ("ingredient_a_id", "=", ingredient_b_id),
                        ("ingredient_b_id", "=", ingredient_a_id),
                    ],
                    limit=1,
                )
                if not rule:
                    continue
                pair = rule.ingredient_a_id | rule.ingredient_b_id
                related_products = therapy_products.filtered(
                    lambda product: bool(
                        product.product_tmpl_id.pharmacy_active_ingredient_ids & pair
                    )
                )
                if not (related_products & products):
                    continue
                description = rule.description
                if rule.recommended_action:
                    description = "%s\n\n%s" % (description, rule.recommended_action)
                prescription._create_clinical_alert(
                    {
                        "alert_type": "interaction",
                        "severity": rule.severity,
                        "title": rule.title,
                        "description": description,
                        "product_ids": [(6, 0, related_products.ids)],
                    }
                )
        return True
