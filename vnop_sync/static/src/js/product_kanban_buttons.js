/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { Domain } from "@web/core/domain";
import { patch } from "@web/core/utils/patch";
import { KanbanController } from "@web/views/kanban/kanban_controller";

const PRODUCT_MODEL = "product.template";
const TEMPLATE_FILE_URL = "/vnop_purchase/static/xlsx/import_san_pham.xlsx";
const CLASSIFICATION_FIELD = "classification_type";
const CLASSIFICATION_LABELS = {
    frame: "Gọng kính",
    lens: "Tròng kính",
    accessory: "Phụ kiện",
    other: "Khác",
};
const VNOP_FACET_KEY = "vnopCategFilter";

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

        // Remove previously injected facet filter (if any) to avoid duplicates
        const existingIds = Object.entries(searchModel.searchItems || {})
            .filter(([, item]) => item[VNOP_FACET_KEY])
            .map(([id]) => Number(id));
        if (existingIds.length) {
            searchModel.query = searchModel.query.filter(
                (q) => !existingIds.includes(q.searchItemId)
            );
            for (const id of existingIds) {
                delete searchModel.searchItems[id];
            }
        }

        const baseDomain = new Domain(this._vnopBaseGlobalDomain || []);
        const extraDomain = value
            ? new Domain([[CLASSIFICATION_FIELD, "=", value]])
            : new Domain([]);
        searchModel.globalDomain = Domain.and([baseDomain, extraDomain]).toList();

        if (value) {
            // Inject a visible facet into the search bar so user sees the active filter
            const newId = Math.max(0, ...Object.keys(searchModel.searchItems).map(Number)) + 1;
            searchModel.searchItems[newId] = {
                id: newId,
                type: "filter",
                description: CLASSIFICATION_LABELS[value] || value,
                domain: `[('${CLASSIFICATION_FIELD}','=','${value}')]`,
                groupId: newId,
                groupNumber: newId,
                [VNOP_FACET_KEY]: true,
            };
            searchModel.query.push({ searchItemId: newId });
        }

        // Invalidate cached domain (search_model.js _domain) so next read recomputes
        searchModel._domain = null;
        searchModel.searchDomain = searchModel._getDomain({ withSearchPanel: false });
        searchModel.search();
    },
});
