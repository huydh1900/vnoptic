import {Component, onWillStart, useRef, useState} from "@odoo/owl";
import {ensureJQuery} from "@web/core/ensure_jquery";
import {sprintf} from "@web/core/utils/strings";

export class AttachmentPreviewWidget extends Component {
    static template = "attachment_preview.AttachmentPreviewWidget";
    static props = {};
    setup() {
        super.setup();
        this.attachments = [];
        this.env.bus.addEventListener(
            "open_attachment_preview",
            ({detail: {attachment_id, attachment_info_list}}) =>
                this._onAttachmentPreview(attachment_id, attachment_info_list)
        );
        this.env.bus.addEventListener("hide_attachment_preview", () => this.hide());
        this.state = useState({activeIndex: 0});
        this.currentRef = useRef("current");
        this.iframeRef = useRef("iframe");
        onWillStart(async () => {
            await ensureJQuery();
        });
    }

    _onCloseClick() {
        this.hide();
    }

    _onPreviousClick() {
        this.previous();
    }

    _onNextClick() {
        this.next();
    }

    _onPopoutClick() {
        if (!this.attachments[this.state.activeIndex]) return;
        window.open(
            this.attachments[this.state.activeIndex].previewUrl,
            "_blank",
            "noopener,noreferrer"
        );
    }

    next() {
        var index = this.state.activeIndex + 1;
        if (index >= this.attachments.length) {
            index = 0;
        }
        this.state.activeIndex = index;
        this.updatePaginator();
        this.loadPreview();
    }

    previous() {
        var index = this.state.activeIndex - 1;
        if (index < 0) {
            index = this.attachments.length - 1;
        }
        this.state.activeIndex = index;
        this.updatePaginator();
        this.loadPreview();
    }

    show() {
        if (this.el) {
            this.el.classList.remove("d-none");
        }
    }

    hide() {
        if (this.el) {
            this.el.classList.add("d-none");
        }
    }

    updatePaginator() {
        var value = sprintf(
            "%s / %s",
            this.state.activeIndex + 1,
            this.attachments.length
        );
        if (this.currentRef.el) {
            this.currentRef.el.textContent = value;
        }
    }

    loadPreview() {
        if (this.attachments.length === 0) {
            if (this.iframeRef.el) {
                this.iframeRef.el.setAttribute("src", "about:blank");
            }
            return;
        }
        var att = this.attachments[this.state.activeIndex];
        if (this.iframeRef.el) {
            this.iframeRef.el.setAttribute("src", att.previewUrl);
        }
    }

    setAttachments(attachments, active_attachment_id) {
        this.attachments = attachments;
        if (!attachments) return;
        for (let i = 0; i < attachments.length; ++i) {
            if (parseInt(attachments[i].id, 10) === active_attachment_id) {
                this.state.activeIndex = i;
            }
        }
        this.updatePaginator();
        this.loadPreview();
    }

    _onAttachmentPreview(attachment_id, attachment_info_list) {
        this.setAttachments(attachment_info_list, attachment_id);
        this.show();
    }
}
