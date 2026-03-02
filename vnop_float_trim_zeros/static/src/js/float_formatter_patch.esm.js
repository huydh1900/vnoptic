/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import {
    formatFloat as baseFormatFloat,
    formatFloatFactor as baseFormatFloatFactor,
} from "@web/views/fields/formatters";
import { FloatField } from "@web/views/fields/float/float_field";

function isNaturalNumber(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return false;
    }
    return Math.abs(value - Math.round(value)) < 1e-12;
}

function formatFloatTrimZeros(value, options = {}) {
    if (isNaturalNumber(value)) {
        return baseFormatFloat(value, { ...options, trailingZeros: false, minDigits: 0 });
    }
    return baseFormatFloat(value, options);
}
formatFloatTrimZeros.extractOptions = baseFormatFloat.extractOptions;

function formatFloatFactorTrimZeros(value, options = {}) {
    const factor = options.factor || 1;
    if (isNaturalNumber(value * factor)) {
        return baseFormatFloatFactor(value, { ...options, trailingZeros: false, minDigits: 0 });
    }
    return baseFormatFloatFactor(value, options);
}
formatFloatFactorTrimZeros.extractOptions = baseFormatFloatFactor.extractOptions;

registry.category("formatters").add("float", formatFloatTrimZeros, { force: true });
registry.category("formatters").add("float_factor", formatFloatFactorTrimZeros, { force: true });

patch(FloatField.prototype, {
    get formattedValue() {
        if (this.state.hasFocus && !this.props.readonly) {
            return this.value ?? "";
        }
        if (
            !this.props.formatNumber ||
            (this.props.inputType === "number" && !this.props.readonly && this.value)
        ) {
            return this.value;
        }
        const options = {
            digits: this.props.digits,
            minDigits: this.props.minDigits,
            field: this.props.record.fields[this.props.name],
        };
        if (this.props.humanReadable && !this.state.hasFocus) {
            return formatFloatTrimZeros(this.value, {
                ...options,
                humanReadable: true,
                decimals: this.props.decimals,
            });
        }
        return formatFloatTrimZeros(this.value, { ...options, humanReadable: false });
    },
});
