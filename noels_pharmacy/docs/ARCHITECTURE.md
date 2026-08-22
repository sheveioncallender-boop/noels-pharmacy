# Architecture

## Design boundary

The pharmacy suite adds clinical and regulatory controls around native Odoo transactions. It does not recreate stock, accounting, customer, Sales, POS, Website or payment engines.

| Pharmacy need | Authoritative record |
|---|---|
| Customer/purchaser | `res.partner` |
| Patient clinical profile | `pharmacy.patient`, linked to `res.partner` |
| Medicine/catalog/price/tax | `product.template` / `product.product` |
| Lot and expiry | Native `stock.lot` |
| Quotation/order | Native `sale.order` |
| POS receipt/payment | Native `pos.order` |
| Stock deduction | Native Sales/POS stock operation |
| Invoice/accounting | Native Odoo/Odoo Mates records |
| Prescription and refill authority | `pharmacy.prescription` and lines |
| Supply event and remaining balance | `pharmacy.dispensing` and lines |
| Inspection register | Immutable `pharmacy.register.entry` |
| Clinical warning | `pharmacy.clinical.alert` |
| Clinical edit/delete event | Append-only `pharmacy.audit.log` |

## Numbering and state

Capture receives a temporary `TMP` reference. The first confirmed dispensing assigns the permanent no-gap `RX` sequence. Cancelled, reversed and audited records remain visible; permanent numbers are not reused.

Prescription states: `Draft → Awaiting Review → Approved → Partially Dispensed → Dispensed`.

Cancellation is explicit. Confirmed dispensing is reversed with compensating register entries rather than deleted.

## POS boundary

The POS popup creates the draft prescription on the server against the POS order UUID before payment. Uploaded documents and alerts stay in the secured server database. Payment validation checks only regulated products. After native POS payment succeeds, the server links the `pos.order`, creates the dispensing log, and confirms it when all required lot/pharmacist data is ready.

## Security

- Company record rules isolate operational clinical records.
- Pharmacy roles separate capture, approval, reversal, configuration and audit.
- Only the logged-in pharmacist/manager can approve or override a blocking alert.
- Attachments are linked to the secured prescription record.
- Portal routes re-check prescription ownership server-side.
- Regulatory and audit records cannot be edited or deleted through the ORM.

## Clinical content

The engine detects matching allergy ingredients, repeated active ingredients (duplicate therapy), repeated therapeutic classes and configured ingredient interactions. Clinical rules are configuration data and must come from an approved/licensed source; they are not guessed from product names.
