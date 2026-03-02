import {canPreview, showPreview} from "../utils.esm";
import {AttachmentList} from "@mail/core/common/attachment_list";
import {patch} from "@web/core/utils/patch";

patch(AttachmentList.prototype, {
    _onPreviewAttachment(attachment, ev) {
        const target = ev?.currentTarget;
        const split_screen = target?.dataset?.target !== "new";
        showPreview(
            attachment.id,
            attachment.defaultSource || attachment.url || attachment.downloadUrl,
            attachment.extension,
            attachment.filename || attachment.displayName || attachment.name,
            split_screen,
            this.previewableAttachments,
            this.env.bus
        );
    },

    _canPreviewAttachment(attachment) {
        return canPreview(attachment.extension);
    },
});
