/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class PharmacyPrescriptionDialog extends Component {
    static template = "noels_pharmacy.PharmacyPrescriptionDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        orderUuid: String,
        partnerId: { type: Number, optional: true },
        patientName: { type: String, optional: true },
        patientIsCustomer: { type: Boolean, optional: true },
        lines: Array,
        onSaved: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            saving: false,
            patientName: this.props.patientName || "",
            patientIsCustomer: this.props.patientIsCustomer ?? Boolean(this.props.partnerId),
            dateOfBirth: "",
            allergyStatus: "unknown",
            allergyName: "",
            doctorName: "",
            doctorLicense: "",
            prescriptionDate: new Date().toISOString().slice(0, 10),
            diagnosisNotes: "",
            pharmacistInitials: "",
            refillsAllowed: 0,
            sourceType: "physical",
            approveNow: false,
            lines: this.props.lines.map((line) => ({ ...line })),
            attachment: null,
            attachmentName: "",
        });
    }

    async onFileChange(event) {
        const file = event.target.files?.[0];
        if (!file) {
            this.state.attachment = null;
            this.state.attachmentName = "";
            return;
        }
        if (file.size > 10 * 1024 * 1024) {
            this.notification.add(_t("Prescription uploads are limited to 10 MB."), { type: "danger" });
            event.target.value = "";
            return;
        }
        const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        this.state.attachment = { name: file.name, mimetype: file.type || "application/octet-stream", data: String(dataUrl).split(",", 2)[1] };
        this.state.attachmentName = file.name;
    }

    onPatientCustomerChange(event) {
        this.state.patientIsCustomer = event.target.checked;
        if (this.state.patientIsCustomer) {
            this.state.patientName = this.props.patientName || "";
        } else if (this.state.patientName === this.props.patientName) {
            this.state.patientName = "";
        }
    }

    async save() {
        if (!this.state.patientIsCustomer && !this.state.patientName.trim()) {
            this.notification.add(_t("Select a customer or enter the patient's name."), { type: "warning" });
            return;
        }
        if (this.state.lines.some((line) => !line.directions.trim())) {
            this.notification.add(_t("Enter dispensing instructions for every medicine."), { type: "warning" });
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call("pharmacy.prescription", "pos_save_prescription", [{
                order_uuid: this.props.orderUuid,
                partner_id: this.state.patientIsCustomer ? (this.props.partnerId || false) : false,
                purchaser_partner_id: this.props.partnerId || false,
                patient_name: this.state.patientName,
                date_of_birth: this.state.dateOfBirth || false,
                allergy_status: this.state.allergyStatus,
                allergy_name: this.state.allergyName,
                doctor_name: this.state.doctorName,
                doctor_license: this.state.doctorLicense,
                prescription_date: this.state.prescriptionDate,
                diagnosis_notes: this.state.diagnosisNotes,
                pharmacist_initials: this.state.pharmacistInitials,
                refills_allowed: Number(this.state.refillsAllowed || 0),
                source_type: this.state.sourceType,
                approve_now: this.state.approveNow,
                lines: this.state.lines,
                attachment: this.state.attachment,
            }]);
            this.props.onSaved?.(result);
            this.notification.add(
                result.state === "approved" ? _t("Prescription added and approved.") : _t("Prescription added; pharmacist review is pending."),
                { type: result.state === "approved" ? "success" : "warning" }
            );
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    }
}
