# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class VnopSaleReportAging(models.Model):
    _name = 'vnop.sale.report.aging'
    _description = 'Phân tích tuổi nợ - HĐ chưa thanh toán'
    _auto = False
    _order = 'days_overdue desc'

    move_id = fields.Many2one('account.move', string='Hóa đơn', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Khách hàng', readonly=True)
    invoice_date_due = fields.Date(string='Hạn thanh toán', readonly=True)
    amount_residual = fields.Monetary(string='Còn nợ', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Tiền tệ', readonly=True)
    days_overdue = fields.Integer(string='Số ngày quá hạn', readonly=True)
    aging_bucket = fields.Selection(
        selection=[
            ('b_0_30', '0-30 ngày'),
            ('b_31_60', '31-60 ngày'),
            ('b_61_90', '61-90 ngày'),
            ('b_91_180', '91-180 ngày'),
            ('b_over_180', 'Trên 180 ngày'),
        ],
        string='Nhóm nợ',
        readonly=True,
    )
    company_id = fields.Many2one('res.company', string='Công ty', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    row_number() OVER () AS id,
                    am.id AS move_id,
                    am.partner_id,
                    am.invoice_date_due,
                    am.amount_residual,
                    am.currency_id,
                    GREATEST(0, (CURRENT_DATE - am.invoice_date_due)::integer) AS days_overdue,
                    CASE
                        WHEN (CURRENT_DATE - am.invoice_date_due)::integer <= 30 THEN 'b_0_30'
                        WHEN (CURRENT_DATE - am.invoice_date_due)::integer <= 60 THEN 'b_31_60'
                        WHEN (CURRENT_DATE - am.invoice_date_due)::integer <= 90 THEN 'b_61_90'
                        WHEN (CURRENT_DATE - am.invoice_date_due)::integer <= 180 THEN 'b_91_180'
                        ELSE 'b_over_180'
                    END AS aging_bucket,
                    am.company_id
                FROM account_move am
                WHERE am.move_type = 'out_invoice'
                  AND am.state = 'posted'
                  AND am.payment_state IN ('not_paid', 'partial')
                  AND am.amount_residual > 0
            )
        """)
