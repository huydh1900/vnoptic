/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { Component, onMounted, useState } from "@odoo/owl";

const MODEL = "stock.nxt.wizard";
// Số chip hiển thị inline trước khi gộp thành "+N".
const TAG_VISIBLE = 3;
// luxon là global trong Odoo 18 — KHÔNG import (sẽ break asset).
const { DateTime } = luxon;

/**
 * Multi-select dạng chip/tag (port từ SYT-hrm bms_hrm headcount report).
 * props: options [{id,name}], ids [number], placeholder, update(ids).
 */
export class TagSelect extends Component {
    static template = "vnop_stock_nxt.TagSelect";
    static props = {
        options: { type: Array },
        ids: { type: Array },
        placeholder: { type: String, optional: true },
        update: { type: Function },
        showSelectAll: { type: Boolean, optional: true },
    };

    setup() {
        this.state = useState({
            query: "",
            dropdownOpen: false,
            popoverOpen: false,
            popoverSearch: "",
        });
    }

    get selected() {
        const byId = new Map(this.props.options.map((o) => [o.id, o]));
        const out = [];
        for (const id of this.props.ids) {
            const o = byId.get(id);
            if (o) out.push(o);
        }
        return out;
    }
    get visible() { return this.selected.slice(0, TAG_VISIBLE); }
    get hiddenCount() { return Math.max(this.selected.length - TAG_VISIBLE, 0); }

    get allSelected() { return this.props.ids.length === this.props.options.length && this.props.options.length > 0; }

    get filteredOptions() {
        const idSet = new Set(this.props.ids);
        const q = (this.state.query || "").trim().toLowerCase();
        return this.props.options.filter((o) => {
            if (idSet.has(o.id)) return false;
            return !q || (o.name || "").toLowerCase().includes(q);
        });
    }
    get filteredInPopover() {
        const q = (this.state.popoverSearch || "").trim().toLowerCase();
        return q ? this.selected.filter((o) => (o.name || "").toLowerCase().includes(q)) : this.selected;
    }

    onQueryInput(ev) { this.state.query = ev.target.value; this.state.dropdownOpen = true; }
    openDropdown() { this.state.dropdownOpen = true; }
    closeDropdown() { setTimeout(() => { this.state.dropdownOpen = false; }, 150); }

    add(id) {
        if (!this.props.ids.includes(id)) {
            this.props.update([...this.props.ids, id]);
        }
        this.state.query = "";
        this.state.dropdownOpen = false;
    }
    remove(id) { this.props.update(this.props.ids.filter((x) => x !== id)); }
    clearAll() { this.props.update([]); this.state.popoverOpen = false; this.state.popoverSearch = ""; }
    selectAll() { this.props.update(this.props.options.map((o) => o.id)); this.state.dropdownOpen = false; this.state.query = ""; }

    togglePopover() {
        this.state.popoverOpen = !this.state.popoverOpen;
        if (!this.state.popoverOpen) this.state.popoverSearch = "";
    }
    onPopoverSearch(ev) { this.state.popoverSearch = ev.target.value; }
}

export class NxtReport extends Component {
    static template = "vnop_stock_nxt.NxtReport";
    static components = { TagSelect, DateTimeInput };
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: false,
            searched: false,
            exporting: false,
            fromDate: DateTime.now().startOf("month"),
            toDate: DateTime.now(),
            selectedWh: [],
            selectedCls: [],
            search: "",
            onlyMovement: false,
            warehouses: [],
            classifications: [],
            columns: [],
            rows: [],
            count: 0,
            totals: {},
            limited: false,
        });
        onMounted(() => this.loadOptions());
    }

    async loadOptions() {
        const opts = await this.orm.call(MODEL, "get_filter_options", []);
        this.state.warehouses = (opts.warehouses || []).map((w) => ({
            id: w.id,
            name: w.code ? `${w.code} - ${w.name}` : w.name,
        }));
        this.state.classifications = (opts.classifications || []).map((c) => ({
            id: c.id,
            name: c.code ? `${c.code} - ${c.name}` : c.name,
        }));
    }

    onWhUpdate(ids) { this.state.selectedWh = ids; }
    onClsUpdate(ids) { this.state.selectedCls = ids; }
    onFromChange(date) { if (date) { this.state.fromDate = date; } }
    onToChange(date) { if (date) { this.state.toDate = date; } }

    get filters() {
        return {
            from_date: this.state.fromDate ? this.state.fromDate.toISODate() : false,
            to_date: this.state.toDate ? this.state.toDate.toISODate() : false,
            warehouse_ids: this.state.selectedWh,
            classification_ids: this.state.selectedCls,
            search: this.state.search || "",
            only_with_movement: this.state.onlyMovement,
        };
    }

    async onSearch() {
        if (!this.state.fromDate || !this.state.toDate) {
            this.notification.add("Vui lòng chọn Từ ngày và Đến ngày.", { type: "warning" });
            return;
        }
        this.state.loading = true;
        try {
            const res = await this.orm.call(MODEL, "get_preview", [this.filters]);
            this.state.columns = res.columns || [];
            this.state.rows = res.rows || [];
            this.state.count = res.count || 0;
            this.state.totals = res.totals || {};
            this.state.limited = !!res.limited;
            this.state.searched = true;
        } finally {
            this.state.loading = false;
        }
    }

    async onExport() {
        if (!this.state.searched) {
            await this.onSearch();
        }
        this.state.exporting = true;
        try {
            const res = await this.orm.call(MODEL, "export_xlsx", [this.filters]);
            if (res && res.url) {
                this.action.doAction({ type: "ir.actions.act_url", url: res.url, target: "self" });
            }
        } finally {
            this.state.exporting = false;
        }
    }

    onReset() {
        this.state.fromDate = DateTime.now().startOf("month");
        this.state.toDate = DateTime.now();
        this.state.selectedWh = [];
        this.state.selectedCls = [];
        this.state.search = "";
        this.state.onlyMovement = false;
        this.state.rows = [];
        this.state.count = 0;
        this.state.totals = {};
        this.state.limited = false;
        this.state.searched = false;
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            this.onSearch();
        }
    }

    isSubtotal(row) {
        return !!row._subtotal;
    }
    isNum(key) {
        return !!key && (key.startsWith("qty_") || key.startsWith("val_"));
    }
    fmt(value, key) {
        if (this.isNum(key)) {
            return Number(value || 0).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
        }
        return value == null ? "" : value;
    }
}

registry.category("actions").add("vnop_stock_nxt.nxt_report", NxtReport);
