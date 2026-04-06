/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class LensStockMatrix extends Component {
    static template = "vnop_stock.LensStockMatrix";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            sphAxis: [],
            cylAxis: [],
            matrix: {},
            // Giá trị đang gõ trong ô input (chưa áp dụng)
            sphSearchDraft: "",
            cylSearchDraft: "",
            // Giá trị đã apply — chỉ thay đổi khi bấm nút Tìm kiếm / Enter
            sphSearchApplied: "",
            cylSearchApplied: "",
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        const data = await this.orm.call(
            "stock.quant",
            "get_lens_stock_matrix",
            []
        );
        this.state.sphAxis = data.sph_axis || [];
        this.state.cylAxis = data.cyl_axis || [];
        this.state.matrix = data.matrix || {};
        this.state.loading = false;
    }

    /** Axis được lọc theo từ khóa tìm kiếm (so khớp chuỗi trên `name`). */
    _filterAxis(axis, term) {
        const q = (term || "").trim().toLowerCase();
        if (!q) {
            return axis;
        }
        return axis.filter((item) =>
            (item.name || "").toLowerCase().includes(q)
        );
    }

    get filteredSphAxis() {
        return this._filterAxis(this.state.sphAxis, this.state.sphSearchApplied);
    }

    get filteredCylAxis() {
        return this._filterAxis(this.state.cylAxis, this.state.cylSearchApplied);
    }

    onSphSearchInput(ev) {
        this.state.sphSearchDraft = ev.target.value;
    }

    onCylSearchInput(ev) {
        this.state.cylSearchDraft = ev.target.value;
    }

    /** Apply giá trị draft → view mới render theo giá trị đã apply. */
    onApplySearch() {
        this.state.sphSearchApplied = this.state.sphSearchDraft;
        this.state.cylSearchApplied = this.state.cylSearchDraft;
    }

    /** Enter trong ô input = bấm nút Tìm kiếm. */
    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onApplySearch();
        }
    }

    onClearSearch() {
        this.state.sphSearchDraft = "";
        this.state.cylSearchDraft = "";
        this.state.sphSearchApplied = "";
        this.state.cylSearchApplied = "";
    }

    getCell(cylId, sphId) {
        const row = this.state.matrix[cylId];
        if (!row) {
            return 0;
        }
        return row[sphId] || 0;
    }

    /** Tổng theo dòng (CYL) chỉ tính các cột SPH đang hiển thị. */
    getRowTotal(cylId) {
        let total = 0;
        for (const sph of this.filteredSphAxis) {
            total += this.getCell(cylId, sph.id);
        }
        return total;
    }

    /** Tổng theo cột (SPH) chỉ tính các dòng CYL đang hiển thị. */
    getColTotal(sphId) {
        let total = 0;
        for (const cyl of this.filteredCylAxis) {
            total += this.getCell(cyl.id, sphId);
        }
        return total;
    }

    get grandTotal() {
        let total = 0;
        for (const cyl of this.filteredCylAxis) {
            for (const sph of this.filteredSphAxis) {
                total += this.getCell(cyl.id, sph.id);
            }
        }
        return total;
    }

    /**
     * Cell intensity 0..1 relative to the largest VISIBLE cell value.
     * Tính lại theo tập hợp ô đang hiển thị để heat-map phản ánh
     * đúng phạm vi user đang xem.
     */
    getHeat(qty) {
        if (!qty) {
            return 0;
        }
        let max = 0;
        for (const cyl of this.filteredCylAxis) {
            for (const sph of this.filteredSphAxis) {
                const v = this.getCell(cyl.id, sph.id);
                if (v > max) {
                    max = v;
                }
            }
        }
        return max ? qty / max : 0;
    }

    cellStyle(qty) {
        const h = this.getHeat(qty);
        if (!h) {
            return "";
        }
        // Brand-friendly blue gradient.
        const alpha = 0.08 + h * 0.62;
        return `background-color: rgba(45, 115, 222, ${alpha.toFixed(3)});`;
    }

    formatQty(qty) {
        if (!qty) {
            return "";
        }
        return Number.isInteger(qty) ? String(qty) : qty.toFixed(2);
    }
}

registry
    .category("actions")
    .add("vnop_stock.lens_stock_matrix", LensStockMatrix);
