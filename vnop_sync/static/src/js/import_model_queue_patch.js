/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { BaseImportModel } from "@base_import/import_model";

const originalInit = BaseImportModel.prototype.init;
const originalExecuteImport = BaseImportModel.prototype.executeImport;

patch(BaseImportModel.prototype, {
    async init() {
        const sessionId = this.context && this.context.vnop_queue_session_id;
        if (!sessionId) {
            return await originalInit.call(this);
        }

        // Lấy mapping từ context nếu có
        let fields = this.context.vnop_queue_fields || [];
        let columns = this.context.vnop_queue_columns || [];
        let options = this.context.vnop_queue_options || {};

        [this.importTemplates, this.id] = await Promise.all([
            this.orm.call(this.resModel, "get_import_templates", [], {
                context: this.context,
            }),
            this.orm.call("base_import.import", "vnop_create_import_from_queue_session", [sessionId]),
        ]);

        // Gán lại mapping vào model để parse_preview validate đúng
        if (fields.length && columns.length) {
            this.fields = fields;
            this.columns = columns;
        }
        if (options && typeof options === 'object') {
            this.options = options;
        }
    },
    async _executeImportStep(isTest, importRes) {
        const importArgs = [
            this.id,
            importRes.fields,
            importRes.columns,
            this.formattedImportOptions,
        ];
        const response = await this._callImport(isTest, importArgs);
        const {
            ids,
            messages,
            nextrow,
            name,
            error,
            binary_filenames,
            queued,
            queued_session_id,
            queued_rows,
        } = response;

        if (error) {
            return error;
        }

        if (queued) {
            importRes.queued = true;
            importRes.queued_session_id = queued_session_id;
            importRes.queued_rows = queued_rows;
            this.stopImport();
            return false;
        }

        if (ids) {
            importRes.ids = importRes.ids.concat(ids);
        }

        if (messages && messages.length) {
            importRes.hasError = true;
            this.stopImport();
            if (this._handleImportErrors(messages, name)) {
                return false;
            }
        }

        await this._pushLocalImageToRecords(ids, binary_filenames, isTest);

        if (nextrow) {
            this.setOption("skip", nextrow);
            importRes.nextrow = nextrow;
        } else {
            this.stopImport();
        }

        return false;
    },
    async executeImport(isTest = false, totalSteps, importProgress) {
        const data = await originalExecuteImport.call(this, isTest, totalSteps, importProgress);
        if (isTest && data && data.res && data.res.queued) {
            this.importMessages = [];
        }
        return data;
    },
});
