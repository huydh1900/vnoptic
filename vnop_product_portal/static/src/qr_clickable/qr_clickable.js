/** @odoo-module **/

import { ImageField, imageField } from "@web/views/fields/image/image_field";
import { registry } from "@web/core/registry";

export class QrClickableField extends ImageField {
    static template = "vnop_product_portal.QrClickableField";
    static props = {
        ...ImageField.props,
        linkField: { type: String, optional: true },
    };

    get linkUrl() {
        if (!this.props.linkField) {
            return false;
        }
        const url = this.props.record.data[this.props.linkField];
        return url || false;
    }
}

export const qrClickableField = {
    ...imageField,
    component: QrClickableField,
    extractProps: ({ attrs, options }) => ({
        ...imageField.extractProps({ attrs, options }),
        linkField: options.link_field,
    }),
};

registry.category("fields").add("qr_clickable", qrClickableField);
