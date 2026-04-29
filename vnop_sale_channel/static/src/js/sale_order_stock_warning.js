/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useService } from "@web/core/utils/hooks";
import { useEffect } from "@odoo/owl";

// Singleton dedup ở mức module: chỉ 1 cảnh báo tồn kho hiển thị cùng lúc.
// Khi user đóng, onClose reset null → lần fire kế tiếp mới được show.
let activeStockWarningClose = null;

function showStockWarningOnce(notificationService, warnings) {
    if (activeStockWarningClose) {
        return;
    }
    const lines = warnings.map(
        (r) => `• ${r.name}: cần ${r.ordered} ${r.uom}, tồn ${r.available}`
    );
    activeStockWarningClose = notificationService.add(lines.join("\n"), {
        type: "warning",
        sticky: true,
        title: "Cảnh báo tồn kho không đủ",
        onClose: () => {
            activeStockWarningClose = null;
        },
    });
}

patch(FormController.prototype, {
    setup() {
        super.setup();
        if (this.props.resModel !== "sale.order") {
            return;
        }
        this._stockWarningNotification = useService("notification");
        useEffect(
            () => {
                const root = this.model.root;
                if (!root || !root.resId) {
                    return;
                }
                const state = root.data && root.data.state;
                if (state !== "draft" && state !== "sent") {
                    return;
                }
                this._showSaleOrderStockWarning(root.resId);
            },
            () => {
                const root = this.model.root;
                const lineCount =
                    root && root.data && root.data.order_line && root.data.order_line.records
                        ? root.data.order_line.records.length
                        : 0;
                return [
                    root && root.resId,
                    root && root.data && root.data.state,
                    lineCount,
                ];
            }
        );
    },

    async _showSaleOrderStockWarning(orderId) {
        // Nếu đã có 1 cảnh báo đang hiển thị → bỏ qua, không cần gọi RPC.
        if (activeStockWarningClose) {
            return;
        }
        let result;
        try {
            result = await this.orm.call(
                "sale.order",
                "check_stock_warning",
                [[orderId]],
            );
        } catch (e) {
            console.error("[stock_warning] orm call failed", e);
            return;
        }
        if (!Array.isArray(result) || result.length === 0) {
            return;
        }
        showStockWarningOnce(this._stockWarningNotification, result);
    },
});
