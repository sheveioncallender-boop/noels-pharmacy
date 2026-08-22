# Noel's Pharmacy Dispensing for Odoo 19 Community

This is one complete Odoo addon folder. Install the single app named **Noel's Pharmacy Dispensing** to enable the full pharmacy workflow.

## Included in this one module

- Patient profiles with name/contact/address, DOB, gender, blood group, emergency contact, allergies and full history
- Doctors/prescribers, diagnosis, notes and uploaded prescription images/PDFs
- Sequential auditable prescription numbers
- Refills, partial dispensing and remaining balances
- Dedicated partial-fill follow-up queue with patient contact logging and email notification
- Pharmacist approval, initials and dispensing logs
- Backend pharmacist preparation, selectable 3 × 2 / 4 × 2 branded medication labels and scan-to-load POS checkout
- Simple receipt-level expiry records, purchase/receipt expiry capture and expiry monitoring without requiring native lots
- Product-specific low-stock monitoring based on native Odoo On Hand and Forecasted quantities
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

1. Capture the patient, prescription document, doctor, medicines and directions in the Pharmacy app. Change **Supply Now** only when the current fill will be partial.
2. The pharmacist selects **Approve, Prepare & Print**. Clinical checks, the permanent RX number, earliest usable expiry, POS barcode and labels are handled together.
3. Scan the printed `NPX...` Code 128 barcode in POS. Odoo loads the entire prepared prescription.
4. Complete Odoo's normal POS payment. Only then is the dispensing log confirmed, the balance updated, registers posted and native POS stock deducted.

Actual short fills enter **Partial Fills** automatically. Staff can record phone/WhatsApp contact, email the patient, set a follow-up date and later select **Prepare Balance & Print**. Ordinary future refills are tracked but are not placed in the short-fill follow-up queue.

The sequential RX number identifies the clinical prescription. Each prepared fill/refill receives a different secure checkout barcode, preventing an old or paid fill from being cashed twice.

The default label is 3 × 2 inches (76.2 × 50.8 mm), matching the supplied direct-thermal rolls. A 4 × 2 inch option is also included. Either size can be reprinted from the dispensing record without changing the RX number, prepared fill or POS checkout barcode.

## Clinical rule data

The alert engine is included, but interaction rules must be populated from a licensed, pharmacist-approved clinical drug knowledge source. No guessed or unlicensed interaction database is bundled.
