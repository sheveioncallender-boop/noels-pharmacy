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

Capture receives a temporary `TMP` reference. Marking the first fill ready for POS assigns the permanent no-gap `RX` sequence so it can be printed on the medication label. Each fill/refill receives a unique non-clinical `NPX...` checkout token. Cancelled, reversed and audited records remain visible; permanent RX numbers are not reused.

Prescription states: `Draft → Awaiting Review → Approved → Partially Dispensed → Dispensed`.

Cancellation is explicit. Confirmed dispensing is reversed with compensating register entries rather than deleted.

## POS boundary

Prescription capture, clinical checks, approval, fill quantities, lot selection and label printing happen in the backend Pharmacy app. A prepared `pharmacy.dispensing` record is locked in `ready` state and carries a unique checkout barcode. Scanning the barcode in POS retrieves the prepared lines from the server, adds the exact products and quantities to the native cart, and associates the unsaved POS order UUID with that fill.

Payment validation rechecks that the fill is still ready and that regulated quantities match. After native POS payment succeeds, the same prepared record is linked to `pos.order` and confirmed; no second dispensing record and no second stock deduction are created. An unpaid barcode can be invalidated by returning its fill to preparation. A paid barcode cannot be reused.

## Security

- Company record rules isolate operational clinical records.
- Pharmacy roles separate capture, approval, reversal, configuration and audit.
- Only the logged-in pharmacist/manager can approve or override a blocking alert.
- Attachments are linked to the secured prescription record.
- Portal routes re-check prescription ownership server-side.
- Regulatory and audit records cannot be edited or deleted through the ORM.

## Clinical content

The engine detects matching allergy ingredients, repeated active ingredients (duplicate therapy), repeated therapeutic classes and configured ingredient interactions. Clinical rules are configuration data and must come from an approved/licensed source; they are not guessed from product names.
