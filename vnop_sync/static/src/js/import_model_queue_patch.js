/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { BaseImportModel } from "@base_import/import_model";

patch(BaseImportModel.prototype, {
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
});
