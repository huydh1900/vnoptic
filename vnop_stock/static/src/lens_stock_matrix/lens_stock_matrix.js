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
            rowTotals: {},
            colTotals: {},
            grandTotal: 0,
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
        this.state.rowTotals = data.row_totals || {};
        this.state.colTotals = data.col_totals || {};
        this.state.grandTotal = data.grand_total || 0;
        this.state.loading = false;
    }

    async onRefresh() {
        await this.loadData();
    }

    getCell(cylId, sphId) {
        const row = this.state.matrix[cylId];
        if (!row) {
            return 0;
        }
        return row[sphId] || 0;
    }

    /** Cell intensity 0..1 relative to the largest cell value in the matrix. */
    getHeat(qty) {
        if (!qty) {
            return 0;
        }
        let max = 0;
        for (const row of Object.values(this.state.matrix)) {
            for (const v of Object.values(row)) {
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