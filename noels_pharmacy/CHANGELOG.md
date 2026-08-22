# Changelog

## 19.0.4.0.0

- Rebuilt the patient form around a clearly labelled patient name, native contact details, address, DOB, age, gender, blood group, primary doctor, allergies and emergency contact.
- Added patient smart buttons for prescriptions, item-level dispensing history, partial fills and printable history.
- Reduced the core workflow to one pharmacist action: **Approve, Prepare & Print**; labels are then scanned into native POS for payment.
- Added a per-line **Supply Now** quantity so genuine short fills are captured without adding an extra wizard.
- Added a dedicated Partial Fills queue, due dates, phone/WhatsApp contact logging, patient email notifications and one-click balance preparation.
- Kept normal future refills separate from genuine partial-fill follow-up.
- Added simple receipt-level pharmacy expiry records, expected expiry on purchase lines and actual expiry validation on receipts without requiring native lots.
- Added Expiry Monitoring and product smart buttons with earliest-expiry selection for dispensing and label printing.
- Added product-specific low-stock thresholds and Low Stock Monitoring using native Odoo On Hand and Forecasted quantities.
- Added a searchable, exportable, read-only item-level Dispensing Log.
- Added pharmacy expiry details to labels, regulatory registers and inspection CSV exports.

## 19.0.3.0.2

- Rounded custom paper dimensions to whole millimetres as required by Odoo 19's integer `report.paperformat` fields.
- The physical targets remain 3 × 2 inches and 4 × 2 inches using printer-safe 76 × 51 mm and 102 × 51 mm report pages.

## 19.0.3.0.1

- Calibrated medication labels for the Arkscan 2054A direct-thermal printer.
- Added a label-size selector per prepared fill with 3 × 2 inch as the default and 4 × 2 inch as an alternate.
- Added explicit 3 × 2 and 4 × 2 reprint actions without changing the prescription or checkout barcode.
- Reflowed the label into a compact monochrome layout for reliable direct-thermal output.
- Shortened checkout barcode tokens while retaining 48 random bits, improving scan clarity on the smaller stock.
- Added printer, media-calibration and actual-size setup checks to the deployment documentation.

## 19.0.3.0.0

- Replaced cashier-side prescription capture with a backend-first pharmacist workflow.
- Added `Draft / Preparing → Ready for POS → Paid / Dispensed` fill states.
- Added a unique secure `NPX...` checkout barcode per prepared fill/refill.
- Added one-scan POS loading of all prepared medicines, quantities and instructions.
- Added duplicate-scan, expired, already-paid, wrong-quantity and unavailable-POS-product controls.
- Kept payment, stock deduction and receipts in Odoo's native POS flow.
- Rebuilt Noel's medication label with patient, RX, fill date, medicine, instructions, quantity, refills, discard date, prescriber, pharmacist and Code 128 barcode.
- Added auditable label print/reprint counters and invalidation when a fill returns to preparation.

## 19.0.2.0.4

- Granted Odoo system administrators the Pharmacy Manager role automatically through group implication.
- Ensured administrators can see the Noel's Pharmacy app and access all pharmacy menus and configuration after upgrade.

## 19.0.2.0.3

- Updated report action permissions from `groups_id` to Odoo 19's `group_ids` field.
- Applied the fix to the inspection pack and patient prescription history reports.

## 19.0.2.0.2

- Updated all Pharmacy search-view groups for Odoo 19's attribute-free `<group>` syntax.
- Validated the patient, prescription, dispensing, regulatory-register and audit search views together.
- Updated the website product notice to inherit Odoo 19's dedicated `website_sale.cta_wrapper` template.

## 19.0.2.0.1

- Updated pharmacy security groups for Odoo 19's `res.groups.privilege` model.
- Kept operational roles hierarchical while leaving the auditor role independently assignable.
- Updated legacy SQL constraint declarations to Odoo 19 `models.Constraint` declarations.

## 19.0.2.0.0

- Consolidated Core, Sales, POS, Website and Reporting into one installable `noels_pharmacy` module folder.
- Updated all security, report, view, controller and POS asset references for the single-module layout.
- Simplified GitHub and Cloudpepper deployment to one folder and one app installation.

## 19.0.1.0.0

- Added branded pharmacy app and role-based security.
- Added patient, allergy, prescriber and pharmacy staff profiles.
- Added medicine metadata to native Odoo products.
- Added prescriptions, sequential permanent RX numbers, refills and partial balances.
- Added configurable allergy, interaction and duplicate-therapy alerts.
- Added pharmacist approval, documented overrides, dispensing and reversals.
- Added immutable Antibiotic, Controlled Drug and Narcotics registers.
- Added append-only clinical audit events.
- Added branded medication labels.
- Added native Sales order integration.
- Added the original POS prescription capture and payment gate (superseded in 19.0.3.0.0 by backend preparation and barcode checkout).
- Added eCommerce prescription notices/uploads and secured portal history.
- Added Ministry/Board inspection PDF, separate CSV inspection pack and patient history PDF.
