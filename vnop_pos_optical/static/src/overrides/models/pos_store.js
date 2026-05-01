/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { PrescriptionPopup } from "@vnop_pos_optical/overrides/components/prescription_popup/prescription_popup";

// Khi user click sản phẩm có cờ is_optical_lens, mở popup Rx trước khi
// tạo dòng. Nếu user bỏ qua → vẫn tạo dòng nhưng không có Rx (cashier có thể
// edit Rx sau bằng nút trên dòng đơn — implement ở orderline component).
patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        let product = vals.product_id;
        if (typeof product === "number") {
            product = this.data.models["product.product"].get(product);
        }

        if (configure && product && product.is_optical_lens) {
            const payload = await makeAwaitable(this.dialog, PrescriptionPopup, {
                productName: product.display_name || product.name || "",
                startingValue: {},
            });
            // payload === undefined nghĩa là user bấm Bỏ qua/đóng popup → vẫn add dòng,
            // không gắn Rx. Nếu trả về object → merge các trường Rx vào vals.
            if (payload && typeof payload === "object") {
                Object.assign(vals, payload);
            }
        }

        return await super.addLineToOrder(vals, order, opts, configure);
    },
});
