/** @odoo-module **/

import { Orderline } from "@point_of_sale/app/generic_components/orderline/orderline";
import { patch } from "@web/core/utils/patch";

// Owl validate props theo shape — getDisplayData() đã thêm prescriptionSummary
// và uuid nên phải khai báo ở đây, nếu không sẽ lỗi "unknown key".
Orderline.props.line.shape.prescriptionSummary = { type: String, optional: true };
Orderline.props.line.shape.uuid = { type: String, optional: true };

patch(Orderline.prototype, {
    /**
     * Xóa dòng sản phẩm trên giỏ POS. Tra ngược về record qua uuid vì
     * component nhận displayData (plain object), không phải record.
     */
    onRemoveLine(ev) {
        ev.stopPropagation();
        const uuid = this.props.line.uuid;
        if (!uuid) {
            return;
        }
        const order = this.env.services.pos?.get_order();
        if (!order) {
            return;
        }
        let line = order.lines.find((l) => l.uuid === uuid);
        if (!line) {
            return;
        }
        // Combo: xóa từ parent để cascade các line con (theo flow chuẩn ở
        // OrderSummary._setValue).
        if (line.combo_parent_id) {
            line = line.combo_parent_id;
        }
        order.removeOrderline(line);
    },
});
