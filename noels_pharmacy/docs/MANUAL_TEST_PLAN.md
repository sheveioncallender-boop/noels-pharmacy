# Manual acceptance test plan

Run these tests on an Odoo 19 Community staging database cloned from production.

## Setup

- Configure one cashier, pharmacist, manager and auditor.
- Configure an OTC item, an antibiotic, a controlled drug and a narcotic.
- Add active ingredients, one known allergy and one blocking interaction rule.
- Configure tracked lots/expirations for the regulated samples.

## POS

1. Sell only OTC products without opening Prescription; payment must remain native.
2. Add a prescription-required item; payment must stop and direct the cashier to Actions → Prescription.
3. Capture an existing patient and a walk-in patient.
4. Test physical, WhatsApp, email PDF and printed source options.
5. Upload JPG, PNG, WebP and PDF; reject unsupported or over-10-MB files.
6. Enter directions for each line and save before payment.
7. Verify a cashier cannot approve by entering somebody else's initials.
8. Approve as a pharmacist, take native payment, and verify POS ↔ RX ↔ dispensing links.
9. Verify tracked products carry the selected native lot into dispensing.
10. Print the medication label.

## Sales

1. Confirm a normal OTC sale with no extra gate.
2. Attempt to confirm a regulated sale without RX; it must stop.
3. Create the prescription from the quotation, review alerts, approve and confirm.
4. Complete native delivery/invoicing and create the linked dispensing record.
5. Verify Odoo Mates postings match an equivalent non-pharmacy sale.

## Website

1. Verify the regulated-product and cart notices.
2. Sign in, upload a prescription and verify the sale-order link.
3. Approve the prescription and complete native checkout/payment.
4. Verify the customer can see only their own prescription history.

## Clinical and regulatory

1. Confirm an allergy conflict creates a blocking alert.
2. Confirm a configured interaction creates the expected severity.
3. Confirm repeated ingredient/class creates duplicate-therapy warning.
4. Record and verify a pharmacist override reason.
5. Partially dispense, confirm remaining balance, then dispense a refill.
6. Confirm register entries land in every register assigned to the medicine.
7. Reverse a dispensing as manager and verify compensating entries.
8. Attempt edits/deletes of confirmed registers, audit events and dispensing lines.
9. Export the inspection PDF and CSV ZIP and reconcile totals to source records.

## Upgrade and recovery

1. Upgrade the single `noels_pharmacy` module on staging.
2. Reopen POS after asset upgrade.
3. Re-run one OTC and one regulated transaction.
4. Restore the staging backup once to prove database/filestore recovery.
