/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";

const { DateTime } = luxon;

/**
 * KPI Dashboard Tiles: doanh thu hôm nay / tuần này / tháng này + delta % so kỳ trước.
 * Dữ liệu lấy real-time qua ORM readGroup mỗi lần render.
 */
export class DashboardKpiTiles extends Component {
    static template = "vnop_sale_dashboard.KpiTiles";

    setup() {
        this.orm = useService("orm");
        this.company = useService("company");

        this.state = useState({
            tiles: [],
            loading: true,
            error: null,
        });

        onWillStart(async () => {
            await this._loadKpiData();
        });
    }

    /**
     * Tính date range cho một period.
     * @param {"today"|"week"|"month"} period
     * @param {boolean} prior - true = kỳ trước
     * @returns {{ dateFrom: string, dateTo: string }}
     */
    _getDateRange(period, prior = false) {
        const today = DateTime.now();

        let start, end;
        if (period === "today") {
            start = today.startOf("day");
            end = today.endOf("day");
        } else if (period === "week") {
            start = today.startOf("week");
            end = today.endOf("week");
        } else {
            // month
            start = today.startOf("month");
            end = today.endOf("month");
        }

        if (prior) {
            const duration = end.diff(start).plus({ milliseconds: 1 });
            end = start.minus({ milliseconds: 1 });
            start = end.minus(duration).plus({ milliseconds: 1 });
        }

        return {
            dateFrom: start.toFormat("yyyy-MM-dd HH:mm:ss"),
            dateTo: end.toFormat("yyyy-MM-dd HH:mm:ss"),
        };
    }

    /**
     * Thực hiện readGroup cho một khoảng ngày, trả về tổng amount_total.
     */
    async _fetchAmount(dateFrom, dateTo) {
        const companyId = this.company.currentCompany.id;
        const domain = [
            ["state", "in", ["sale", "done"]],
            ["company_id", "=", companyId],
            ["date_order", ">=", dateFrom],
            ["date_order", "<=", dateTo],
        ];
        const result = await this.orm.readGroup(
            "sale.order",
            domain,
            ["amount_total:sum"],
            []
        );
        return result.length > 0 ? (result[0].amount_total || 0) : 0;
    }

    async _loadKpiData() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const periods = ["today", "week", "month"];
            const labels = ["Hôm nay", "Tuần này", "Tháng này"];

            const results = await Promise.all(
                periods.map(async (period, idx) => {
                    const current = this._getDateRange(period, false);
                    const prior = this._getDateRange(period, true);

                    const [currentAmount, priorAmount] = await Promise.all([
                        this._fetchAmount(current.dateFrom, current.dateTo),
                        this._fetchAmount(prior.dateFrom, prior.dateTo),
                    ]);

                    let delta = null;
                    if (priorAmount > 0) {
                        delta = ((currentAmount - priorAmount) / priorAmount) * 100;
                    }

                    return {
                        label: labels[idx],
                        amount: currentAmount,
                        delta,
                    };
                })
            );

            this.state.tiles = results;
        } catch (err) {
            this.state.error = err.message || "Lỗi tải dữ liệu";
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Format số tiền theo currency công ty hiện tại.
     * currentCompany.currency_id là object {id, name, ...} từ company service.
     */
    formatAmount(amount) {
        const currencyId = this.company.currentCompany.currency_id?.id
            || this.company.currentCompany.currency_id;
        return formatMonetary(amount, { currencyId });
    }

    /**
     * Format delta % với dấu + / - và 1 chữ số thập phân.
     */
    formatDelta(delta) {
        if (delta === null || delta === undefined) {
            return "—";
        }
        const sign = delta >= 0 ? "+" : "";
        return `${sign}${delta.toFixed(1)}%`;
    }

    /**
     * CSS class cho badge delta.
     */
    deltaClass(delta) {
        if (delta === null || delta === undefined) {
            return "text-muted";
        }
        return delta >= 0 ? "text-success" : "text-danger";
    }

    async onRefresh() {
        await this._loadKpiData();
    }
}

registry.category("actions").add("vnop_sale_dashboard_kpi_tiles", DashboardKpiTiles);
