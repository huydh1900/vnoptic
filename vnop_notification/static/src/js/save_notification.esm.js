/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { ListController } from "@web/views/list/list_controller";

patch(FormController.prototype, {
    async save(params) {
        const res = await super.save(...arguments);
        if (res !== false) {
            this.env.services.notification.add("Lưu bản ghi thành công", {
                type: "success",
            });
        }
        return res;
    },
});

patch(ListController.prototype, {
    get deleteConfirmationDialogProps() {
        const props = super.deleteConfirmationDialogProps;
        const selectedCount = this.model.root.selection.length;
        const originalConfirm = props.confirm;
        const notificationService = this.env.services.notification;
        props.confirm = async () => {
            await originalConfirm();
            notificationService.add(
                `Đã xóa ${selectedCount} bản ghi thành công`,
                { type: "success" }
            );
        };
        return props;
    },
});
