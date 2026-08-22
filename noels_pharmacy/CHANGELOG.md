# Changelog

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
- Added POS Actions prescription capture, secure upload, approval/payment gate and paid-order dispensing.
- Added eCommerce prescription notices/uploads and secured portal history.
- Added Ministry/Board inspection PDF, separate CSV inspection pack and patient history PDF.
