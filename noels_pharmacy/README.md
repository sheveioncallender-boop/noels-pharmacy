# Noel's Pharmacy Dispensing for Odoo 19 Community

This is one complete Odoo addon folder. Install the single app named **Noel's Pharmacy Dispensing** to enable the full pharmacy workflow.

## Included in this one module

- Patient profiles, allergies, DOB and full prescription history
- Doctors/prescribers, diagnosis, notes and uploaded prescription images/PDFs
- Sequential auditable prescription numbers
- Refills, partial dispensing and remaining balances
- Pharmacist approval, initials and dispensing logs
- Medication directions and branded medication labels
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

## Clinical rule data

The alert engine is included, but interaction rules must be populated from a licensed, pharmacist-approved clinical drug knowledge source. No guessed or unlicensed interaction database is bundled.

