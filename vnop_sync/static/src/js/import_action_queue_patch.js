/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ImportAction } from "@base_import/import_action/import_action";
import { ImportDataProgress } from "@base_import/import_data_progress/import_data_progress";
import { onMounted } from "@odoo/owl";

const originalSetup = ImportAction.prototype.setup;

patch(ImportAction.prototype, {
    setup() {
        originalSetup.call(this);

        onMounted(async () => {
            const context = this.props?.action?.params?.context || this.model?.context || {};
            const sessionId = context.vnop_queue_session_id;
            if (!sessionId) {
                return;
            }

            this.model.block(_t("Đang kiểm tra lại dữ liệu..."));
            // Force re-validate preview (dryrun) to show all errors
            const { res, error } = await this.model.updateData(true);
            if (error) {
                this.state.previewError = error;
            } else {
                this.state.fileLength = res.file_length;
                this.state.previewError = undefined;
            }
            if (context.vnop_queue_session_file_name) {
                this.state.filename = context.vnop_queue_session_file_name;
            }

            if (context.vnop_queue_error_log) {
                this.state.previewError = context.vnop_queue_error_log;
            }

            // Disable 'Nhập' button if any errors exist in preview
            this.state.importDisabled = false;
            if (
                context.vnop_queue_state === 'error' ||
                this.state.previewError ||
                (res && res.messages && res.messages.some(m => m.type === 'error'))
            ) {
                this.state.importDisabled = true;
            }
            this.model.unblock();
        });
    },
    async handleImport(isTest = true) {
        if (!isTest && this.state.importDisabled) {
            this.notification.add(_t("Không thể nhập: Dữ liệu chưa hợp lệ hoặc còn lỗi."), { type: "danger" });
            return;
        }
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
        if (res.queued) {
            const queuedRows = res.queued_rows || 0;
            const messageText = isTest
                ? _t("Queued %(rows)s rows for background testing.", { rows: queuedRows })
                : _t("Queued %(rows)s rows for background import.", { rows: queuedRows });
            this.notification.add(messageText, { type: "success" });
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
