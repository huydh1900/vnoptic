/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { KanbanController } from "@web/views/kanban/kanban_controller";

const PRODUCT_MODEL = "product.template";

patch(KanbanController.prototype, {
    get isProductTemplate() {
        return this.props.resModel === PRODUCT_MODEL;
    },

    async onImportProduct() {
        // TODO: implement import product wizard
    },

    async onExportTemplate() {
        await this.actionService.doAction("vnop_sync.action_product_export_template_wizard");
    },
});
