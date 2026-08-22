# Manual acceptance test plan

Run these tests on an Odoo 19 Community staging database cloned from production.

## Setup

- Configure one cashier, pharmacist, manager and auditor.
- Configure an OTC item, an antibiotic, a controlled drug and a narcotic.
- Add active ingredients, one known allergy and one blocking interaction rule.
- Configure tracked lots/expirations for the regulated samples.
- Install and calibrate the Arkscan 2054A with 3 × 2 inch direct-thermal stock; have 4 × 2 inch stock available for the alternate-size test.

## POS

1. Sell only OTC products normally; payment must remain native.
2. Add a prescription-required item manually; payment must stop and direct the cashier to prepare it in the Pharmacy app and scan its barcode.
3. In the Pharmacy app, capture an existing patient and a walk-in/new patient.
4. Test physical, WhatsApp, email PDF and printed source options.
5. Upload JPG, PNG, WebP and PDF; reject unsupported or over-10-MB files.
6. Add medicines and complete directions for every line.
7. Submit, run clinical checks and approve as the logged-in pharmacist.
8. Select **Prepare for POS**, verify current fill quantities, lot/batch and discard dates.
9. Leave the label size at 3 × 2, select **Ready for POS & Print Labels**, and verify one correctly scaled label per prepared medication with no clipping.
10. Scan any printed `NPX...` checkout barcode and verify the complete fill loads once, with the patient/RX confirmation shown.
11. Scan the same barcode again and verify products are not duplicated.
12. Take native payment and verify POS ↔ RX ↔ prepared fill links, dispensing confirmation, patient history and register entries.
13. Scan the paid barcode again and verify it is blocked as already dispensed.
14. Prepare a refill and verify it receives a new barcode while retaining the original RX number.
15. Return an unpaid fill to preparation and verify its old printed barcode becomes invalid.
16. Prepare another fill with 4 × 2 selected and verify the PDF/media size and barcode scan.
17. Reprint the same ready fill using both explicit size buttons; confirm its RX number and checkout barcode remain unchanged and every print is logged.

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
3. Re-run one OTC transaction and one backend-prepared/barcode-scanned prescription transaction.
4. Restore the staging backup once to prove database/filestore recovery.
