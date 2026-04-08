/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class VnopImportHistoryPanel extends Component {
    static template = "vnop_sync.ImportQueueHistoryPanel";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.user = useService("user");
        this.state = useState({
            loading: true,
            records: [],
            error: "",
        });
        onWillStart(() => this.reload());
    }

    get historyDomain() {
        return [
            ["res_model", "=", "product.template"],
            ["requested_by", "=", this.user.userId],
        ];
    }

    async reload() {
        this.state.loading = true;
        this.state.error = "";
        try {
            this.state.records = await this.orm.searchRead(
                "product.import.queue.session",
                this.historyDomain,
                [
                    "file_name",
                    "state",
                    "total_rows",
                    "processed_rows",
                    "success_count",
                    "error_count",
                    "create_date",
                ],
                {
                    order: "id desc",
                    limit: 20,
                }
            );
        } catch (error) {
            this.state.error = error?.message || _t("Cannot load import history.");
            this.state.records = [];
        } finally {
            this.state.loading = false;
        }
    }

    openRecord(recordId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Import History"),
            res_model: "product.import.queue.session",
            res_id: recordId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openList() {
        this.action.doAction("vnop_sync.action_product_import_queue_session");
    }

    getStateLabel(state) {
        const labels = {
            draft: _t("Draft"),
            queued: _t("Queued"),
            running: _t("Running"),
            done: _t("Done"),
            error: _t("Error"),
        };
        return labels[state] || state;
    }
}
