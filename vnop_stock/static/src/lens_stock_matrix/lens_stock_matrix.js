/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useRef, useState } from "@odoo/owl";

// Mặc định ma trận chỉ hiển thị độ trong khoảng [-3, +3].
const DEFAULT_AXIS_MIN = -3;
const DEFAULT_AXIS_MAX = 3;

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
            // Chỉ giá trị đã apply mới cần reactive — thay đổi sẽ re-render bảng.
            sphSearchApplied: "",
            cylSearchApplied: "",
        });

        // Draft giữ ngoài reactive state để không re-render mỗi keystroke.
        this._sphDraft = "";
        this._cylDraft = "";
        this.sphInputRef = useRef("sphInput");
        this.cylInputRef = useRef("cylInput");

        // Memo cho stats (totals + maxCell) — invalidate theo filter + identity matrix.
        this._statsCache = null;
        this._statsKey = null;
        this._statsMatrixRef = null;

        // Dùng onMounted (không await) để shell + skeleton loading hiển thị ngay
        // khi mở action, data matrix đổ vào sau khi server trả về.
        onMounted(() => {
            this.loadData();
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

    /**
     * Lọc trục hiển thị:
     * - Không có search → giới hạn mặc định [DEFAULT_AXIS_MIN, DEFAULT_AXIS_MAX].
     * - Có search → tìm trong toàn bộ axis, không áp giới hạn mặc định.
     */
    _filterAxis(axis, term) {
        const q = (term || "").trim().toLowerCase();
        if (!q) {
            return axis.filter(
                (item) =>
                    item.value >= DEFAULT_AXIS_MIN &&
                    item.value <= DEFAULT_AXIS_MAX
            );
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

    /**
     * Tính toàn bộ aggregate (row totals, col totals, grand total, max cell)
     * trong một lần duyệt ma trận. Kết quả cache lại theo filter + identity
     * của `state.matrix` để các getter chỉ đọc dict O(1) trong cùng render cycle.
     */
    get stats() {
        const sphAxis = this.filteredSphAxis;
        const cylAxis = this.filteredCylAxis;
        const key = `${this.state.sphSearchApplied}|${this.state.cylSearchApplied}|${sphAxis.length}|${cylAxis.length}`;
        if (
            this._statsKey === key &&
            this._statsMatrixRef === this.state.matrix &&
            this._statsCache
        ) {
            return this._statsCache;
        }

        const matrix = this.state.matrix;
        const rowTotals = {};
        const colTotals = {};
        let grandTotal = 0;
        let maxCell = 0;

        for (const cyl of cylAxis) {
            const row = matrix[cyl.id];
            if (!row) {
                continue;
            }
            let rt = 0;
            for (const sph of sphAxis) {
                const v = row[sph.id] || 0;
                if (!v) {
                    continue;
                }
                rt += v;
                colTotals[sph.id] = (colTotals[sph.id] || 0) + v;
                if (v > maxCell) {
                    maxCell = v;
                }
            }
            if (rt) {
                rowTotals[cyl.id] = rt;
                grandTotal += rt;
            }
        }

        this._statsKey = key;
        this._statsMatrixRef = matrix;
        this._statsCache = { rowTotals, colTotals, grandTotal, maxCell };
        return this._statsCache;
    }

    onSphSearchInput(ev) {
        this._sphDraft = ev.target.value;
    }

    onCylSearchInput(ev) {
        this._cylDraft = ev.target.value;
    }

    /** Apply giá trị draft → view mới render theo giá trị đã apply. */
    onApplySearch() {
        this.state.sphSearchApplied = this._sphDraft;
        this.state.cylSearchApplied = this._cylDraft;
    }

    /** Enter trong ô input = bấm nút Tìm kiếm. */
    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onApplySearch();
        }
    }

    onClearSearch() {
        this._sphDraft = "";
        this._cylDraft = "";
        if (this.sphInputRef.el) {
            this.sphInputRef.el.value = "";
        }
        if (this.cylInputRef.el) {
            this.cylInputRef.el.value = "";
        }
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
        return this.stats.rowTotals[cylId] || 0;
    }

    /** Tổng theo cột (SPH) chỉ tính các dòng CYL đang hiển thị. */
    getColTotal(sphId) {
        return this.stats.colTotals[sphId] || 0;
    }

    get grandTotal() {
        return this.stats.grandTotal;
    }

    cellStyle(qty) {
        if (!qty) {
            return "";
        }
        const max = this.stats.maxCell;
        if (!max) {
            return "";
        }
        // Brand-friendly blue gradient — heat 0..1 so với cell lớn nhất đang hiển thị.
        const alpha = 0.08 + (qty / max) * 0.62;
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
