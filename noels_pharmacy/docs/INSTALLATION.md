# Cloudpepper installation and upgrade

## 1. Deploy the repository

1. Create a private Git repository for the pharmacy deployment.
2. Drag the single `noels_pharmacy` folder into the repository root and commit it to the deployment branch used by Cloudpepper.
3. In Cloudpepper, add the repository root to the Odoo addons path.
4. Deploy/pull the branch and restart the Odoo 19 service.
5. In developer mode, update the Apps list.

Do not copy or patch files inside Odoo core.

## 2. Install the module

Install the single app:

1. **Noel's Pharmacy Dispensing**

Its manifest installs the required native Sales, POS, Website/eCommerce, Portal, Inventory and supporting Odoo dependencies. It does not replace their native workflows.

## 3. Configure before live use

1. Assign pharmacy roles under **Settings → Users**: Pharmacy User / Cashier, Pharmacist, Pharmacy Manager, or Pharmacy Auditor.
2. Create one pharmacy staff profile for every operating user and record unique initials. Pharmacists/managers should also have licence numbers.
3. Mark pharmacy products and configure generic name, strength, dosage form, prescription/approval requirements, active ingredients, therapeutic class, register membership, directions, cautions, and native lot/expiry tracking.
4. Load pharmacist-approved drug interaction rules with a source/reference.
5. Confirm the company name/address/phone and report layout.
6. Install the Arkscan 2054A driver on every label-printing workstation and connect the printer by USB.
7. Load the 3 × 2 inch direct-thermal stock, run the printer's media calibration, and set the driver stock size to 3 × 2 inches in landscape orientation.
8. Print at Actual Size / 100%. Disable browser headers, footers, Fit to Page and any extra margins. The PDF already contains the correct page size.
9. For the included 4 × 2 inch option, load matching direct-thermal media and change the driver stock size to 4 × 2 before printing.
10. Configure the barcode scanner in keyboard mode with an Enter suffix, then test an `NPX...` Code 128 label in POS.
11. Close and reopen POS sessions after installing or upgrading POS assets.

## 4. Production acceptance checks

Follow `docs/MANUAL_TEST_PLAN.md` on a cloned/staging database. Verify the native Sales, POS payment, Inventory, invoice and Odoo Mates posting flows before production cutover.

## Upgrade

1. Back up the database and filestore.
2. Deploy a tagged release to staging.
3. Restart Odoo and upgrade `noels_pharmacy`.
4. Run the acceptance checks.
5. Deploy the same tag to production and upgrade the same module.

Never delete prescription, dispensing, register or audit rows directly in PostgreSQL. Use documented cancellation/reversal actions.
