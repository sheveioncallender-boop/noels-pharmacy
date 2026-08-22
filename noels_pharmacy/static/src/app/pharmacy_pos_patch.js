/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

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
        const reference = this.currentOrder?.uiState?.pharmacyPrescription?.reference;
        return reference ? _t("Prescription %s", reference) : _t("Prescription Ready");
    },
});

function barcodeValue(code) {
    return String(code?.base_code || code?.code || code || "").trim().toUpperCase();
}

patch(ProductScreen.prototype, {
    async _barcodeErrorAction(code) {
        const barcode = barcodeValue(code);
        if (!barcode.startsWith("NPX")) {
            return super._barcodeErrorAction(...arguments);
        }

        const order = this.currentOrder || this.pos.getOrder();
        const currentPrescription = order.uiState?.pharmacyPrescription;
        if (currentPrescription?.barcode === barcode) {
            this.env.services.notification.add(_t("This prescription is already loaded."), {
                type: "warning",
            });
            return;
        }
        if (currentPrescription?.exists) {
            this.dialog.add(AlertDialog, {
                title: _t("Prescription Already Loaded"),
                body: _t("Complete or remove the current prescription order before scanning another one."),
            });
            return;
        }

        const result = await this.env.services.orm.call(
            "pharmacy.dispensing",
            "pos_load_prepared_checkout",
            [barcode, order.uuid]
        );
        if (!result.ok) {
            this.dialog.add(AlertDialog, {
                title: _t("Prescription Cannot Be Loaded"),
                body: result.message,
            });
            return;
        }

        const products = [];
        const missing = [];
        for (const item of result.lines) {
            const product = this.pos.models["product.product"].get(item.product_id);
            if (!product) {
                missing.push(item.name);
            } else {
                products.push({ item, product });
            }
        }
        if (missing.length) {
            this.dialog.add(AlertDialog, {
                title: _t("Medicine Not Available in this POS"),
                body: _t("Enable these medicines in the POS and reload the session: %s", missing.join(", ")),
            });
            return;
        }

        for (const { item, product } of products) {
            await this.pos.addLineToCurrentOrder(
                {
                    product_id: product,
                    qty: item.quantity,
                    customer_note: item.instructions || "",
                },
                {},
                false
            );
        }

        const partner = this.pos.models["res.partner"]?.get(result.purchaser_partner_id);
        if (partner && !order.getPartner()) {
            order.setPartner(partner);
        }
        order.uiState.pharmacyPrescription = result;
        this.env.services.notification.add(
            _t("%s loaded for %s.", result.reference, result.patient_name),
            { type: "success" }
        );
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
