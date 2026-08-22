# Noel's Pharmacy Dispensing for Odoo 19 Community

This is one complete Odoo addon folder. Install the single app named **Noel's Pharmacy Dispensing** to enable the full pharmacy workflow.

## Included in this one module

- Patient profiles, allergies, DOB and full prescription history
- Doctors/prescribers, diagnosis, notes and uploaded prescription images/PDFs
- Sequential auditable prescription numbers
- Refills, partial dispensing and remaining balances
- Pharmacist approval, initials and dispensing logs
- Backend pharmacist preparation, selectable 3 × 2 / 4 × 2 branded medication labels and scan-to-load POS checkout
- Allergy, duplicate therapy and configurable drug interaction alerts
- Separate antibiotic, controlled-drug and narcotic registers
- Append-only audit history and reversible dispensing entries
- Native Sales, Point of Sale and Website/eCommerce integration
- Ministry/Pharmacy Board inspection reports, PDF histories and CSV audit exports

## GitHub and Cloudpepper

1. Create an empty GitHub repository.
2. Drag the `noels_pharmacy` folder into the repository root and commit it.
3. Connect the repository/branch to Cloudpepper.
4. Ensure the repository root is included in Odoo's custom addons path.
5. Update the Apps List, search for `Noel's Pharmacy Dispensing`, and install it.

The manifest installs the required native Odoo apps automatically. Odoo's existing Sales, POS, Website, Inventory, accounting and payment flows are extended, not replaced.

Install and complete the checklist in `docs/MANUAL_TEST_PLAN.md` on a staging database before using it in production.

## Dispensing workflow

1. Capture the patient, prescriber, prescription document and medicine directions in the Pharmacy app.
2. Submit and approve the prescription as a pharmacist.
3. Select **Prepare for POS**, verify the current fill quantities/lots, choose the label size, then select **Ready for POS & Print Labels**.
4. Scan the printed `NPX...` Code 128 barcode in POS. Odoo loads the full prepared fill and identifies it as a prescription.
5. Complete Odoo's normal POS payment. Only then is the dispensing log confirmed, the refill balance updated, registers posted and native POS stock deducted.

The sequential RX number identifies the clinical prescription. Each prepared fill/refill receives a different secure checkout barcode, preventing an old or paid fill from being cashed twice.

The default label is 3 × 2 inches (76.2 × 50.8 mm), matching the supplied direct-thermal rolls. A 4 × 2 inch option is also included. Either size can be reprinted from the dispensing record without changing the RX number, prepared fill or POS checkout barcode.

## Clinical rule data

The alert engine is included, but interaction rules must be populated from a licensed, pharmacist-approved clinical drug knowledge source. No guessed or unlicensed interaction database is bundled.
