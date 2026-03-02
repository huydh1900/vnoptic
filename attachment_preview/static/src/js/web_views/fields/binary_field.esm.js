import {canPreview, showPreview} from "../../utils.esm";
import {BinaryField} from "@web/views/fields/binary/binary_field";
import {_t} from "@web/core/l10n/translation";
import {onMounted} from "@odoo/owl";
import {patch} from "@web/core/utils/patch";
import {sprintf} from "@web/core/utils/strings";
import {useService} from "@web/core/utils/hooks";

patch(BinaryField.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        onMounted(() => this._preview_onMounted());
    },

    async _preview_onMounted() {
        if (this.props.record.resId) {
            const extension = await this.orm.call(
                "ir.attachment",
                "get_binary_extension",
                [
                    this.props.record.resModel,
                    this.props.record.resId,
                    this.props.name,
                    this.props.fileNameField,
                ]
            );
            if (canPreview(extension)) {
                this._renderPreviewButton(extension);
            }
        }
    },

    _renderPreviewButton(extension) {
        const root = this.el;
        if (!root) return;
        const dlButton = root.querySelector("button.fa-download");
        if (!dlButton) return;
        if (root.querySelector("button.o_attachment_preview_button")) return;

        const previewButton = document.createElement("button");
        previewButton.className =
            "btn btn-secondary fa fa-external-link o_attachment_preview_button";
        previewButton.setAttribute("data-tooltip", _t("Preview"));
        previewButton.setAttribute("aria-label", _t("Preview"));
        previewButton.setAttribute("title", _t("Preview"));
        previewButton.dataset.extension = extension;
        previewButton.addEventListener("click", this._onPreview.bind(this));
        dlButton.insertAdjacentElement("afterend", previewButton);
    },

    _onPreview(event) {
        showPreview(
            null,
            sprintf(
                "/web/content?model=%s&field=%s&id=%s",
                this.props.record.resModel,
                this.props.name,
                this.props.record.resId
            ),
            event.currentTarget.dataset.extension,
            sprintf(_t("Preview %s"), this.fileName),
            false,
            null,
            this.env.bus
        );
        event.stopPropagation();
    },
});
