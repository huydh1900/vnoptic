/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { Domain } from "@web/core/domain";
import { patch } from "@web/core/utils/patch";
import { KanbanController } from "@web/views/kanban/kanban_controller";

const PRODUCT_MODEL = "product.template";
const TEMPLATE_FILE_URL = "/vnop_purchase/static/xlsx/import_san_pham.xlsx";
const CLASSIFICATION_FIELD = "classification_type";

patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.props.resModel === PRODUCT_MODEL) {
            // Snapshot the action's base globalDomain to recombine on each filter change
            this._vnopBaseGlobalDomain = this.env.searchModel.globalDomain;
        }
    },

    get isProductTemplate() {
        return this.props.resModel === PRODUCT_MODEL;
    },

    async onImportProduct() {
        await this.actionService.doAction("vnop_sync.action_product_import_wizard");
    },

    onExportTemplate() {
        browser.location.href = TEMPLATE_FILE_URL;
    },

    onCategFilterChange(ev) {
        const value = ev.target.value;
        const searchModel = this.env.searchModel;
        const baseDomain = new Domain(this._vnopBaseGlobalDomain || []);
        const extraDomain = value
            ? new Domain([[CLASSIFICATION_FIELD, "=", value]])
            : new Domain([]);
        searchModel.globalDomain = Domain.and([baseDomain, extraDomain]).toList();
        // Invalidate cached domain (search_model.js _domain) so next read recomputes from globalDomain
        searchModel._domain = null;
        searchModel.searchDomain = searchModel._getDomain({ withSearchPanel: false });
        searchModel.search();
    },
});
