/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { PharmacyPrescriptionDialog } from "./pharmacy_prescription_dialog";

function pharmacyOrderLines(order) {
    return order.lines
        .filter((line) => line.getQuantity() > 0 && line.product_id.product_tmpl_id.is_pharmacy_item)
        .map((line) => {
            const template = line.product_id.product_tmpl_id;
            return { product_id: line.product_id.id, name: line.product_id.display_name, quantity: line.getQuantity(), directions: template.pharmacy_default_directions || "" };
        });
}

patch(ControlButtons.prototype, {
    get pharmacyPrescriptionLabel() {
        return this.currentOrder?.uiState?.pharmacyPrescription?.exists ? _t("Prescription Added") : _t("Prescription");
    },
    async clickPharmacyPrescription() {
        const order = this.currentOrder;
        const lines = pharmacyOrderLines(order);
        if (!lines.length) {
            this.dialog.add(AlertDialog, { title: _t("No Pharmacy Medicine"), body: _t("Add at least one product marked as a pharmacy medicine first.") });
            return;
        }
        const partner = order.getPartner();
        this.dialog.add(PharmacyPrescriptionDialog, {
            orderUuid: order.uuid,
            partnerId: partner?.id,
            patientName: order.uiState.pharmacyPrescription?.patient_name || partner?.name || "",
            patientIsCustomer: order.uiState.pharmacyPrescription?.patient_is_customer ?? Boolean(partner),
            lines,
            onSaved: (result) => { order.uiState.pharmacyPrescription = result; },
        });
    },
});

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate = false) {
        const result = await this.env.services.orm.call("pharmacy.prescription", "pos_validate_for_payment", [this.currentOrder.uuid, pharmacyOrderLines(this.currentOrder)]);
        if (!result.ok) {
            this.dialog.add(AlertDialog, { title: _t("Prescription Required"), body: result.message });
            return;
        }
        return super.validateOrder(isForceValidate);
    },
});

patch(ReceiptScreen.prototype, {
    get hasPharmacyMedicine() {
        return Boolean(this.currentOrder.uiState.pharmacyPrescription?.exists);
    },
    async printPharmacyLabels() {
        if (!this.currentOrder.isSynced) {
            this.notification.add(_t("Wait for the order to finish syncing, then try again."), { type: "warning" });
            return;
        }
        const labelWindow = window.open("", "_blank");
        const result = await this.env.services.orm.call(
            "pos.order",
            "action_get_pharmacy_label_pdf",
            [[this.currentOrder.id]]
        );
        const bytes = Uint8Array.from(atob(result.data), (character) => character.charCodeAt(0));
        const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
        if (labelWindow) {
            labelWindow.opener = null;
            labelWindow.location.href = url;
        } else {
            this.notification.add(_t("Allow pop-ups to open the medication label PDF."), { type: "warning" });
        }
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    },
});
