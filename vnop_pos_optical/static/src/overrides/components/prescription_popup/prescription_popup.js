/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

// Rx step-precision Vietnam optical convention.
const SPH_STEP = 0.25;
const CYL_STEP = 0.25;
const ADD_STEP = 0.25;
const AXIS_STEP = 1;
const PD_STEP = 0.5;

const SPH_MIN = -20;
const SPH_MAX = 20;
const CYL_MIN = -10;
const CYL_MAX = 10;
const ADD_MIN = 0;
const ADD_MAX = 4;
const AXIS_MIN = 0;
const AXIS_MAX = 180;
const PD_MIN = 40;
const PD_MAX = 80;

function clamp(value, min, max) {
    if (value < min) return min;
    if (value > max) return max;
    return value;
}

function roundStep(value, step) {
    // Avoid float drift (vd 0.1 + 0.2 != 0.3) khi cộng lặp lại trên +/- click.
    const factor = 1 / step;
    return Math.round(value * factor) / factor;
}

export class PrescriptionPopup extends Component {
    static template = "vnop_pos_optical.PrescriptionPopup";
    static components = { Dialog };
    static props = {
        productName: { type: String, optional: true },
        startingValue: { type: Object, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        productName: "",
        startingValue: {},
    };

    setup() {
        const sv = this.props.startingValue || {};
        this.state = useState({
            rx_od_sph: sv.rx_od_sph || 0,
            rx_od_cyl: sv.rx_od_cyl || 0,
            rx_od_axis: sv.rx_od_axis || 0,
            rx_od_add: sv.rx_od_add || 0,
            rx_os_sph: sv.rx_os_sph || 0,
            rx_os_cyl: sv.rx_os_cyl || 0,
            rx_os_axis: sv.rx_os_axis || 0,
            rx_os_add: sv.rx_os_add || 0,
            rx_pd: sv.rx_pd || 0,
            rx_note: sv.rx_note || "",
        });
    }

    get title() {
        return this.props.productName
            ? _t("Nhập đơn kính - %s", this.props.productName)
            : _t("Nhập đơn kính");
    }

    // Bảng cấu hình meta cho từng field — dùng cho UI render lẫn +/- handler.
    get fieldMeta() {
        return {
            rx_od_sph: { step: SPH_STEP, min: SPH_MIN, max: SPH_MAX, decimals: 2 },
            rx_od_cyl: { step: CYL_STEP, min: CYL_MIN, max: CYL_MAX, decimals: 2 },
            rx_od_axis: { step: AXIS_STEP, min: AXIS_MIN, max: AXIS_MAX, decimals: 0 },
            rx_od_add: { step: ADD_STEP, min: ADD_MIN, max: ADD_MAX, decimals: 2 },
            rx_os_sph: { step: SPH_STEP, min: SPH_MIN, max: SPH_MAX, decimals: 2 },
            rx_os_cyl: { step: CYL_STEP, min: CYL_MIN, max: CYL_MAX, decimals: 2 },
            rx_os_axis: { step: AXIS_STEP, min: AXIS_MIN, max: AXIS_MAX, decimals: 0 },
            rx_os_add: { step: ADD_STEP, min: ADD_MIN, max: ADD_MAX, decimals: 2 },
            rx_pd: { step: PD_STEP, min: PD_MIN, max: PD_MAX, decimals: 1 },
        };
    }

    formatValue(field) {
        const meta = this.fieldMeta[field];
        if (!meta) return this.state[field];
        const value = Number(this.state[field] || 0);
        return value.toFixed(meta.decimals);
    }

    increment(field) {
        const meta = this.fieldMeta[field];
        if (!meta) return;
        const current = Number(this.state[field] || 0);
        this.state[field] = clamp(roundStep(current + meta.step, meta.step), meta.min, meta.max);
    }

    decrement(field) {
        const meta = this.fieldMeta[field];
        if (!meta) return;
        const current = Number(this.state[field] || 0);
        this.state[field] = clamp(roundStep(current - meta.step, meta.step), meta.min, meta.max);
    }

    onInputChange(field, ev) {
        const meta = this.fieldMeta[field];
        if (!meta) {
            this.state[field] = ev.target.value;
            return;
        }
        const raw = parseFloat(ev.target.value.replace(",", "."));
        if (Number.isNaN(raw)) {
            this.state[field] = 0;
            return;
        }
        this.state[field] = clamp(roundStep(raw, meta.step), meta.min, meta.max);
    }

    onNoteChange(ev) {
        this.state.rx_note = ev.target.value;
    }

    confirm() {
        // Trim note để không lưu khoảng trắng vô nghĩa.
        const note = (this.state.rx_note || "").trim();
        this.props.getPayload({
            rx_od_sph: this.state.rx_od_sph,
            rx_od_cyl: this.state.rx_od_cyl,
            rx_od_axis: this.state.rx_od_axis,
            rx_od_add: this.state.rx_od_add,
            rx_os_sph: this.state.rx_os_sph,
            rx_os_cyl: this.state.rx_os_cyl,
            rx_os_axis: this.state.rx_os_axis,
            rx_os_add: this.state.rx_os_add,
            rx_pd: this.state.rx_pd,
            rx_note: note,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
