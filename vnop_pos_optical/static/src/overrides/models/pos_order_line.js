/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

const RX_FIELDS = [
    "rx_od_sph", "rx_od_cyl", "rx_od_axis", "rx_od_add",
    "rx_os_sph", "rx_os_cyl", "rx_os_axis", "rx_os_add",
    "rx_pd",
];

patch(PosOrderline.prototype, {
    /**
     * Hai dòng có Rx khác nhau (hoặc 1 có Rx 1 không) phải giữ riêng,
     * không được gộp như sản phẩm thông thường — vì mỗi đôi kính cắt theo Rx
     * là sản phẩm vật lý duy nhất.
     */
    can_be_merged_with(orderline) {
        if (!super.can_be_merged_with(orderline)) {
            return false;
        }
        if (this.hasPrescription() || orderline.hasPrescription()) {
            return false;
        }
        return true;
    },

    hasPrescription() {
        if (this.rx_note && this.rx_note.trim()) {
            return true;
        }
        for (const f of RX_FIELDS) {
            const v = this[f];
            if (v && Number(v) !== 0) {
                return true;
            }
        }
        return false;
    },

    /**
     * Render gọn cho hiển thị trên cart line (1 dòng tóm tắt Rx).
     * Format: "OD: -2.50/-0.75x180 +1.00 | OS: -2.25/0x0 +1.00 | PD 62"
     */
    getPrescriptionSummary() {
        if (!this.hasPrescription()) {
            return "";
        }
        const fmt = (v, digits = 2) => {
            const n = Number(v || 0);
            return n.toFixed(digits);
        };
        const od = `OD: ${fmt(this.rx_od_sph)}/${fmt(this.rx_od_cyl)}x${Math.round(this.rx_od_axis || 0)} +${fmt(this.rx_od_add)}`;
        const os = `OS: ${fmt(this.rx_os_sph)}/${fmt(this.rx_os_cyl)}x${Math.round(this.rx_os_axis || 0)} +${fmt(this.rx_os_add)}`;
        const pd = this.rx_pd ? ` | PD ${fmt(this.rx_pd, 1)}` : "";
        const note = this.rx_note ? ` | ${this.rx_note}` : "";
        return `${od} | ${os}${pd}${note}`;
    },

    /**
     * Bơm prescriptionSummary vào display data — Orderline template đọc qua
     * t-slot mở rộng (xem orderline_inherit.xml).
     */
    getDisplayData() {
        return {
            ...super.getDisplayData(),
            prescriptionSummary: this.getPrescriptionSummary(),
        };
    },
});
