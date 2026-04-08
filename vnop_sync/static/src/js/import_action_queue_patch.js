/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ImportAction } from "@base_import/import_action/import_action";
import { ImportDataProgress } from "@base_import/import_data_progress/import_data_progress";

import { VnopImportHistoryPanel } from "./import_queue_history_panel";

ImportAction.components = {
    ...ImportAction.components,
    VnopImportHistoryPanel,
};

patch(ImportAction.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.activeTab = "mapping";
    },

    get showHistoryTab() {
        return this.resModel === "product.template";
    },

    switchImportTab(tabName) {
        this.state.activeTab = tabName;
    },

    async handleImport(isTest = true) {
        const message = isTest ? _t("Testing") : _t("Importing");

        let blockComponent;
        if (this.isBatched) {
            blockComponent = {
                class: ImportDataProgress,
                props: {
                    stopImport: () => this.stopImport(),
                    totalSteps: this.totalSteps,
                    importProgress: this.state.importProgress,
                },
            };
        }

        this.model.block(message, blockComponent);

        let res = { ids: [] };
        try {
            const data = await this.model.executeImport(
                isTest,
                this.totalSteps,
                this.state.importProgress
            );
            res = data.res;
        } finally {
            this.model.unblock();
        }

        if (!isTest && res.queued) {
            const queuedRows = res.queued_rows || 0;
            this.notification.add(_t("Queued %(rows)s rows for background import.", { rows: queuedRows }), {
                type: "success",
            });
            this.exit();
            return;
        }

        if (!isTest && res.nextrow) {
            this.state.isPaused = true;
        }

        if (!isTest && res.ids.length) {
            if (res.hasError) {
                return;
            }
            this.notification.add(_t("%s records successfully imported", res.ids.length), {
                type: "success",
            });
            this.exit(res.ids);
        }
    },
});
