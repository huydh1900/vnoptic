/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useExternalListener, useRef, useState } from "@odoo/owl";

// Mặc định: SPH dọc [-20, +6], CYL ngang [-4, 0].
// Khi user search/chọn mẫu mắt thì bỏ giới hạn này, tìm trong toàn bộ axis.
const DEFAULT_SPH_MIN = -20;
const DEFAULT_SPH_MAX = 6;
const DEFAULT_CYL_MIN = -4;
const DEFAULT_CYL_MAX = 0;

// Cap số option render trong popup lens để tránh đơ khi dataset lớn.
const LENS_POPUP_MAX_VISIBLE = 100;
// SPH có ~200 selection values, CYL ~40. Cap để tránh khựng khi mở popup.
const AXIS_POPUP_MAX_VISIBLE = 80;
const LENS_SEARCH_DEBOUNCE_MS = 180;

export class LensStockMatrix extends Component {
    static template = "vnop_stock.LensStockMatrix";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: false,
            searched: false,
            sphAxis: [],
            cylAxis: [],
            matrix: {},
            // Nhóm mắt (product.classification, category_type='lens').
            lensClassifications: [],
            classificationId: "",
            // Danh sách "mẫu mắt" cho selector + giá trị đang chọn.
            lensModels: [],
            lensKey: "",
            lensSearch: "",
            lensPickerOpen: false,
            // Chỉ giá trị đã apply mới cần reactive — thay đổi sẽ re-render bảng.
            sphSearchApplied: "",
            cylSearchApplied: "",
            // Draft pick hiện tại (hiển thị trên trigger), commit khi nhấn Tìm kiếm.
            sphDraft: "",
            cylDraft: "",
            // Popup state cho SPH/CYL picker.
            sphPickerOpen: false,
            cylPickerOpen: false,
            sphPopupSearch: "",
            cylPopupSearch: "",
        });

        this.sphBoxRef = useRef("sphBox");
        this.cylBoxRef = useRef("cylBox");
        this.lensBoxRef = useRef("lensBox");
        this.lensSearchInputRef = useRef("lensSearchInput");
        this.sphSearchInputRef = useRef("sphSearchInput");
        this.cylSearchInputRef = useRef("cylSearchInput");

        useExternalListener(document, "mousedown", (ev) => this._onDocMouseDown(ev));

        // Memo cho stats (totals + maxCell) — invalidate theo filter + identity matrix.
        this._statsCache = null;
        this._statsKey = null;
        this._statsMatrixRef = null;
        // Memo cho axis đã filter — tránh O(N*M) lặp lại mỗi td trong tbody.
        this._axisCache = null;
        this._axisKey = null;
        this._axisMatrixRef = null;

        onMounted(() => {
            this.loadInitial();
        });
    }

    async loadInitial() {
        // Load metadata + matrix mặc định (tất cả nhóm / lens / sph / cyl).
        this.state.loading = true;
        const [classifications, models, data] = await Promise.all([
            this.orm.call("stock.quant", "get_lens_classifications", []),
            this.orm.call("stock.quant", "get_lens_models", []),
            this.orm.call("stock.quant", "get_lens_stock_matrix", []),
        ]);
        this.state.lensClassifications = classifications || [];
        this.state.lensModels = models || [];
        this._applyMatrix(data);
        this.state.loading = false;
        this.state.searched = true;
    }

    /** Reload lens models khi đổi nhóm — không động vào matrix. */
    async reloadLensModels() {
        const clsId = this.state.classificationId
            ? parseInt(this.state.classificationId, 10)
            : null;
        const models = await this.orm.call("stock.quant", "get_lens_models", [clsId]);
        this.state.lensModels = models || [];
        if (
            this.state.lensKey &&
            !this.state.lensModels.some((m) => m.key === this.state.lensKey)
        ) {
            this.state.lensKey = "";
        }
    }

    /** Load matrix theo bộ điều kiện hiện tại — gọi khi user nhấn Tìm kiếm. */
    async loadMatrix() {
        this.state.loading = true;
        const clsId = this.state.classificationId
            ? parseInt(this.state.classificationId, 10)
            : null;
        const data = await this.orm.call("stock.quant", "get_lens_stock_matrix", [
            this.state.lensKey || null,
            clsId,
        ]);
        this._applyMatrix(data);
        this.state.loading = false;
        this.state.searched = true;
    }

    _applyMatrix(data) {
        this.state.sphAxis = data.sph_axis || [];
        this.state.cylAxis = data.cyl_axis || [];
        this.state.matrix = data.matrix || {};
    }

    _axisNum(item) {
        // name dạng "-1.25" hoặc "+1.25" → parseFloat OK.
        const n = parseFloat(item.name);
        return Number.isFinite(n) ? n : 0;
    }

    /**
     * Tính {baseSph, baseCyl, filteredSph, filteredCyl} một lần và cache.
     * Trước đây mỗi td trong tbody gọi `filteredCylAxis` lại → O(rows×40×rows)
     * lặp lại mỗi click. Cache theo applied filter + identity matrix.
     */
    _computeAxes() {
        const sphTerm = (this.state.sphSearchApplied || "").trim().toLowerCase();
        const cylTerm = (this.state.cylSearchApplied || "").trim().toLowerCase();
        const key = `${sphTerm}|${cylTerm}`;
        if (
            this._axisCache &&
            this._axisKey === key &&
            this._axisMatrixRef === this.state.matrix
        ) {
            return this._axisCache;
        }
        const matrix = this.state.matrix;
        const baseSph = sphTerm
            ? this.state.sphAxis.filter((it) =>
                  (it.name || "").toLowerCase().includes(sphTerm)
              )
            : this.state.sphAxis.filter((it) => {
                  const v = this._axisNum(it);
                  return v >= DEFAULT_SPH_MIN && v <= DEFAULT_SPH_MAX;
              });
        const baseCyl = cylTerm
            ? this.state.cylAxis.filter((it) =>
                  (it.name || "").toLowerCase().includes(cylTerm)
              )
            : this.state.cylAxis.filter((it) => {
                  const v = this._axisNum(it);
                  return v >= DEFAULT_CYL_MIN && v <= DEFAULT_CYL_MAX;
              });
        // Đánh dấu CYL có ít nhất 1 cell trong baseSph → loại cột empty.
        const cylHasData = new Set();
        const sphHasData = new Set();
        for (const sph of baseSph) {
            const row = matrix[sph.id];
            if (!row) continue;
            for (const cyl of baseCyl) {
                if (row[cyl.id]) {
                    cylHasData.add(cyl.id);
                    sphHasData.add(sph.id);
                }
            }
        }
        const filteredSph = baseSph.filter((s) => sphHasData.has(s.id));
        const filteredCyl = baseCyl.filter((c) => cylHasData.has(c.id));
        this._axisCache = { baseSph, baseCyl, filteredSph, filteredCyl };
        this._axisKey = key;
        this._axisMatrixRef = matrix;
        return this._axisCache;
    }

    get _baseSphAxis() { return this._computeAxes().baseSph; }
    get _baseCylAxis() { return this._computeAxes().baseCyl; }
    get filteredSphAxis() { return this._computeAxes().filteredSph; }
    get filteredCylAxis() { return this._computeAxes().filteredCyl; }

    /** Filter danh sách mẫu mắt theo từ khoá nhập ở selector. */
    get filteredLensModels() {
        const q = (this.state.lensSearch || "").trim().toLowerCase();
        if (!q) {
            return this.state.lensModels;
        }
        return this.state.lensModels.filter((m) =>
            (m.name || "").toLowerCase().includes(q)
        );
    }

    /** Cap số dòng render để tránh đơ khi list dài. */
    get visibleLensModels() {
        const all = this.filteredLensModels;
        if (all.length <= LENS_POPUP_MAX_VISIBLE) {
            return all;
        }
        return all.slice(0, LENS_POPUP_MAX_VISIBLE);
    }

    get lensOverflow() {
        return this.filteredLensModels.length > LENS_POPUP_MAX_VISIBLE;
    }

    /**
     * Tính toàn bộ aggregate (row totals, col totals, grand total, max cell)
     * trong một lần duyệt ma trận. Cache theo filter + identity của matrix.
     * Lưu ý: matrix giờ keyed theo SPH (row) → CYL (col).
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

        for (const sph of sphAxis) {
            const row = matrix[sph.id];
            if (!row) {
                continue;
            }
            let rt = 0;
            for (const cyl of cylAxis) {
                const v = row[cyl.id] || 0;
                if (!v) {
                    continue;
                }
                rt += v;
                colTotals[cyl.id] = (colTotals[cyl.id] || 0) + v;
                if (v > maxCell) {
                    maxCell = v;
                }
            }
            if (rt) {
                rowTotals[sph.id] = rt;
                grandTotal += rt;
            }
        }

        this._statsKey = key;
        this._statsMatrixRef = matrix;
        this._statsCache = { rowTotals, colTotals, grandTotal, maxCell };
        return this._statsCache;
    }

    onApplySearch() {
        this.state.sphSearchApplied = this.state.sphDraft;
        this.state.cylSearchApplied = this.state.cylDraft;
        this.state.sphPickerOpen = false;
        this.state.cylPickerOpen = false;
        this.state.lensPickerOpen = false;
        this.loadMatrix();
    }

    onClearSph() {
        this.state.sphDraft = "";
        this.state.sphSearchApplied = "";
        this.state.sphPopupSearch = "";
        if (this.sphSearchInputRef.el) this.sphSearchInputRef.el.value = "";
        this.state.sphPickerOpen = false;
    }

    onClearCyl() {
        this.state.cylDraft = "";
        this.state.cylSearchApplied = "";
        this.state.cylPopupSearch = "";
        if (this.cylSearchInputRef.el) this.cylSearchInputRef.el.value = "";
        this.state.cylPickerOpen = false;
    }

    onClearSearch() {
        this.state.sphDraft = "";
        this.state.cylDraft = "";
        this.state.sphSearchApplied = "";
        this.state.cylSearchApplied = "";
    }

    /** Reset toàn bộ filter (Nhóm, Lens, SPH, CYL) về default và reload matrix. */
    async onClearAllFilters() {
        if (this._lensSearchTimer) {
            clearTimeout(this._lensSearchTimer);
            this._lensSearchTimer = null;
        }
        if (this._sphSearchTimer) {
            clearTimeout(this._sphSearchTimer);
            this._sphSearchTimer = null;
        }
        if (this._cylSearchTimer) {
            clearTimeout(this._cylSearchTimer);
            this._cylSearchTimer = null;
        }
        this.state.classificationId = "";
        this.state.lensKey = "";
        this.state.lensSearch = "";
        this.state.sphDraft = "";
        this.state.cylDraft = "";
        this.state.sphSearchApplied = "";
        this.state.cylSearchApplied = "";
        this.state.sphPopupSearch = "";
        this.state.cylPopupSearch = "";
        this.state.lensPickerOpen = false;
        this.state.sphPickerOpen = false;
        this.state.cylPickerOpen = false;
        if (this.lensSearchInputRef.el) this.lensSearchInputRef.el.value = "";
        if (this.sphSearchInputRef.el) this.sphSearchInputRef.el.value = "";
        if (this.cylSearchInputRef.el) this.cylSearchInputRef.el.value = "";
        // Reload lens models toàn bộ (không lọc nhóm) + matrix default.
        await this.reloadLensModels();
        await this.loadMatrix();
    }

    onToggleSphPicker() {
        this.state.sphPickerOpen = !this.state.sphPickerOpen;
        if (this.state.sphPickerOpen) {
            setTimeout(() => {
                if (this.sphSearchInputRef.el) this.sphSearchInputRef.el.focus();
            }, 0);
        }
    }

    onToggleCylPicker() {
        this.state.cylPickerOpen = !this.state.cylPickerOpen;
        if (this.state.cylPickerOpen) {
            setTimeout(() => {
                if (this.cylSearchInputRef.el) this.cylSearchInputRef.el.focus();
            }, 0);
        }
    }

    onCloseSphPicker() { this.state.sphPickerOpen = false; }
    onCloseCylPicker() { this.state.cylPickerOpen = false; }

    onSphPopupSearchInput(ev) {
        const value = ev.target.value;
        if (this._sphSearchTimer) clearTimeout(this._sphSearchTimer);
        this._sphSearchTimer = setTimeout(() => {
            this._sphSearchTimer = null;
            this.state.sphPopupSearch = value;
        }, LENS_SEARCH_DEBOUNCE_MS);
    }

    onCylPopupSearchInput(ev) {
        const value = ev.target.value;
        if (this._cylSearchTimer) clearTimeout(this._cylSearchTimer);
        this._cylSearchTimer = setTimeout(() => {
            this._cylSearchTimer = null;
            this.state.cylPopupSearch = value;
        }, LENS_SEARCH_DEBOUNCE_MS);
    }

    onSphPopupKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onApplySearch();
        } else if (ev.key === "Escape") {
            this.state.sphPickerOpen = false;
        }
    }

    onCylPopupKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onApplySearch();
        } else if (ev.key === "Escape") {
            this.state.cylPickerOpen = false;
        }
    }

    onPickSph(value) {
        this.state.sphDraft = value || "";
        this.state.sphPickerOpen = false;
    }

    onPickCyl(value) {
        this.state.cylDraft = value || "";
        this.state.cylPickerOpen = false;
    }

    _onDocMouseDown(ev) {
        if (this.state.sphPickerOpen && this.sphBoxRef.el && !this.sphBoxRef.el.contains(ev.target)) {
            this.state.sphPickerOpen = false;
        }
        if (this.state.cylPickerOpen && this.cylBoxRef.el && !this.cylBoxRef.el.contains(ev.target)) {
            this.state.cylPickerOpen = false;
        }
        if (this.state.lensPickerOpen && this.lensBoxRef.el && !this.lensBoxRef.el.contains(ev.target)) {
            this.state.lensPickerOpen = false;
        }
    }

    /** Tập SPH/CYL có data thuộc lens đã chọn — cache theo identity của matrix. */
    get _matrixSphKeys() {
        if (this._matrixSphKeysRef !== this.state.matrix) {
            this._matrixSphKeysRef = this.state.matrix;
            this._matrixSphKeysCache = new Set(Object.keys(this.state.matrix));
        }
        return this._matrixSphKeysCache;
    }
    get _matrixCylKeys() {
        if (this._matrixCylKeysRef !== this.state.matrix) {
            this._matrixCylKeysRef = this.state.matrix;
            const s = new Set();
            for (const row of Object.values(this.state.matrix)) {
                for (const k of Object.keys(row)) s.add(k);
            }
            this._matrixCylKeysCache = s;
        }
        return this._matrixCylKeysCache;
    }

    /** Options cho dropdown SPH: lọc theo lens đang chọn + theo text gõ. */
    get _sphDropdownAll() {
        let list = this.state.sphAxis;
        if (this.state.lensKey || this.state.classificationId) {
            const used = this._matrixSphKeys;
            list = list.filter((it) => used.has(it.id));
        }
        const q = (this.state.sphPopupSearch || "").trim().toLowerCase();
        if (q) {
            list = list.filter((it) => (it.name || "").toLowerCase().includes(q));
        }
        return list;
    }
    get sphDropdownOptions() {
        const all = this._sphDropdownAll;
        return all.length > AXIS_POPUP_MAX_VISIBLE
            ? all.slice(0, AXIS_POPUP_MAX_VISIBLE)
            : all;
    }
    get sphDropdownOverflow() {
        return this._sphDropdownAll.length > AXIS_POPUP_MAX_VISIBLE;
    }
    get sphDropdownTotal() {
        return this._sphDropdownAll.length;
    }

    get _cylDropdownAll() {
        let list = this.state.cylAxis;
        if (this.state.lensKey || this.state.classificationId) {
            const used = this._matrixCylKeys;
            list = list.filter((it) => used.has(it.id));
        }
        const q = (this.state.cylPopupSearch || "").trim().toLowerCase();
        if (q) {
            list = list.filter((it) => (it.name || "").toLowerCase().includes(q));
        }
        return list;
    }
    get cylDropdownOptions() {
        const all = this._cylDropdownAll;
        return all.length > AXIS_POPUP_MAX_VISIBLE
            ? all.slice(0, AXIS_POPUP_MAX_VISIBLE)
            : all;
    }
    get cylDropdownOverflow() {
        return this._cylDropdownAll.length > AXIS_POPUP_MAX_VISIBLE;
    }
    get cylDropdownTotal() {
        return this._cylDropdownAll.length;
    }

    onLensSearchInput(ev) {
        const value = ev.target.value;
        if (this._lensSearchTimer) {
            clearTimeout(this._lensSearchTimer);
        }
        this._lensSearchTimer = setTimeout(() => {
            this._lensSearchTimer = null;
            this.state.lensSearch = value;
        }, LENS_SEARCH_DEBOUNCE_MS);
    }

    onLensSearchKeydown(ev) {
        if (ev.key === "Escape") {
            this.state.lensPickerOpen = false;
        }
    }

    onToggleLensPicker() {
        this.state.lensPickerOpen = !this.state.lensPickerOpen;
        if (this.state.lensPickerOpen) {
            setTimeout(() => {
                if (this.lensSearchInputRef.el) {
                    this.lensSearchInputRef.el.focus();
                }
            }, 0);
        }
    }

    onCloseLensPicker() {
        this.state.lensPickerOpen = false;
    }

    onPickLens(key) {
        this.state.lensKey = key || "";
        this.state.lensPickerOpen = false;
    }

    get selectedLensName() {
        if (!this.state.lensKey) return "";
        const found = this.state.lensModels.find((m) => m.key === this.state.lensKey);
        return found ? found.name : "";
    }

    onClearLens() {
        if (this._lensSearchTimer) {
            clearTimeout(this._lensSearchTimer);
            this._lensSearchTimer = null;
        }
        this.state.lensKey = "";
        this.state.lensSearch = "";
        if (this.lensSearchInputRef.el) {
            this.lensSearchInputRef.el.value = "";
        }
        this.state.lensPickerOpen = false;
    }

    /** Đổi nhóm mắt — chỉ reload danh sách mẫu mắt cho cascade dropdown. */
    onClassificationChange(ev) {
        this.state.classificationId = ev.target.value || "";
        this.reloadLensModels();
    }

    onClearClassification() {
        this.state.classificationId = "";
        this.reloadLensModels();
    }

    /** Click vào 1 cell → mở list stock.quant đã filter theo SPH/CYL (+ lens/nhóm). */
    async onCellClick(sphId, cylId) {
        const qty = this.getCell(sphId, cylId);
        if (!qty) return;
        const clsId = this.state.classificationId
            ? parseInt(this.state.classificationId, 10)
            : null;
        const action = await this.orm.call(
            "stock.quant",
            "action_open_lens_stock_cell",
            [sphId, cylId, this.state.lensKey || null, clsId],
        );
        this.action.doAction(action);
    }

    /** Cell: row=SPH, col=CYL. */
    getCell(sphId, cylId) {
        const row = this.state.matrix[sphId];
        if (!row) {
            return 0;
        }
        return row[cylId] || 0;
    }

    /** Tổng theo dòng SPH — chỉ tính CYL đang hiển thị. */
    getRowTotal(sphId) {
        return this.stats.rowTotals[sphId] || 0;
    }

    /** Tổng theo cột CYL — chỉ tính SPH đang hiển thị. */
    getColTotal(cylId) {
        return this.stats.colTotals[cylId] || 0;
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
