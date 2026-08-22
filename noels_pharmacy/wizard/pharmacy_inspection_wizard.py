import base64
import csv
import io
import json
import zipfile
from datetime import timedelta

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class PharmacyInspectionWizard(models.TransientModel):
    _name = "pharmacy.inspection.wizard"
    _description = "Pharmacy Inspection Report"

    date_from = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    register_type_id = fields.Many2one(
        "pharmacy.register.type",
        string="Limit to Register",
        help="Leave blank to include separate Antibiotic, Controlled Drug and Narcotics sections.",
    )
    export_file = fields.Binary(readonly=True)
    export_filename = fields.Char(readonly=True)

    def _check_dates(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise ValidationError(_("The end date cannot be before the start date."))

    def _datetime_domain(self, field_name):
        self.ensure_one()
        start = fields.Datetime.to_datetime(self.date_from)
        end = fields.Datetime.to_datetime(self.date_to + timedelta(days=1))
        return [(field_name, ">=", start), (field_name, "<", end)]

    def _prescriptions(self):
        self.ensure_one()
        return self.env["pharmacy.prescription"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("prescription_date", ">=", self.date_from),
                ("prescription_date", "<=", self.date_to),
            ],
            order="prescription_date, name, id",
        )

    def _dispensing_lines(self):
        self.ensure_one()
        return self.env["pharmacy.dispensing.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("dispensing_id.state", "in", ("confirmed", "reversed")),
                *self._datetime_domain("dispensing_id.dispensed_at"),
            ],
            order="dispensing_id, id",
        )

    def _register_types(self):
        self.ensure_one()
        if self.register_type_id:
            return self.register_type_id
        return self.env["pharmacy.register.type"].search(
            [("code", "in", ("antibiotic", "controlled", "narcotic"))], order="sequence, name"
        )

    def _register_entries(self, register_type):
        self.ensure_one()
        return self.env["pharmacy.register.entry"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("register_type_id", "=", register_type.id),
                *self._datetime_domain("entry_datetime"),
            ],
            order="entry_datetime, id",
        )

    def _audit_events(self):
        self.ensure_one()
        return self.env["pharmacy.audit.log"].search(
            [
                ("company_id", "=", self.company_id.id),
                *self._datetime_domain("event_datetime"),
            ],
            order="event_datetime, id",
        )

    def action_print_pdf(self):
        self._check_dates()
        return self.env.ref("noels_pharmacy.action_report_inspection_pack").report_action(self)

    @staticmethod
    def _write_csv(archive, filename, headers, rows):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)
        archive.writestr(filename, stream.getvalue().encode("utf-8-sig"))

    def action_export_csv_pack(self):
        self._check_dates()
        self.ensure_one()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            prescriptions = self._prescriptions()
            self._write_csv(
                archive,
                "prescriptions.csv",
                ["RX Number", "Patient", "DOB", "Doctor", "Prescription Date", "Diagnosis/Notes", "Refills", "Status", "Source"],
                [
                    [
                        rx.name,
                        rx.patient_id.name,
                        rx.patient_id.date_of_birth or "",
                        rx.prescriber_id.name or "",
                        rx.prescription_date,
                        rx.diagnosis_notes or "",
                        rx.refills_allowed,
                        rx.state,
                        rx.source_type,
                    ]
                    for rx in prescriptions
                ],
            )
            dispensing_lines = self._dispensing_lines()
            self._write_csv(
                archive,
                "dispensing_log.csv",
                ["Dispensing", "RX Number", "Date Dispensed", "Patient", "Medicine", "Quantity Supplied", "UoM", "Remaining Balance", "Pharmacist Initials", "Lot/Batch", "Source", "State"],
                [
                    [
                        line.dispensing_id.name,
                        line.dispensing_id.prescription_id.name,
                        line.dispensing_id.dispensed_at,
                        line.dispensing_id.patient_id.name,
                        line.product_id.display_name,
                        line.quantity,
                        line.product_uom_id.name,
                        line.remaining_after,
                        line.dispensing_id.pharmacist_initials,
                        line.lot_id.name or "",
                        line.dispensing_id.source_reference or line.dispensing_id.source_type,
                        line.dispensing_id.state,
                    ]
                    for line in dispensing_lines
                ],
            )
            for register_type in self._register_types():
                entries = self._register_entries(register_type)
                filename = "%s_register.csv" % register_type.code.replace(" ", "_")
                self._write_csv(
                    archive,
                    filename,
                    ["Date/Time", "Movement", "RX Number", "Patient", "Doctor", "Medicine", "Lot/Batch", "Qty In", "Qty Out", "UoM", "Pharmacist Initials", "Source"],
                    [
                        [
                            entry.entry_datetime,
                            entry.movement_type,
                            entry.prescription_id.name or "",
                            entry.patient_id.name or "",
                            entry.prescriber_id.name or "",
                            entry.product_id.display_name,
                            entry.lot_id.name or "",
                            entry.quantity_in,
                            entry.quantity_out,
                            entry.product_uom_id.name,
                            entry.pharmacist_id.initials or "",
                            entry.source_reference or "",
                        ]
                        for entry in entries
                    ],
                )
            events = self._audit_events()
            self._write_csv(
                archive,
                "audit_log.csv",
                ["Date/Time", "User", "Action", "Model", "Record", "Old Values", "New Values"],
                [
                    [
                        event.event_datetime,
                        event.user_id.name,
                        event.action,
                        event.model_name,
                        event.record_name,
                        json.dumps(event.old_values or {}, default=str, sort_keys=True),
                        json.dumps(event.new_values or {}, default=str, sort_keys=True),
                    ]
                    for event in events
                ],
            )
        filename = "Noels_Pharmacy_Inspection_%s_to_%s.zip" % (self.date_from, self.date_to)
        self.write({"export_file": base64.b64encode(buffer.getvalue()), "export_filename": filename})
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=pharmacy.inspection.wizard&id=%s&field=export_file&filename_field=export_filename&download=true" % self.id,
            "target": "self",
        }
