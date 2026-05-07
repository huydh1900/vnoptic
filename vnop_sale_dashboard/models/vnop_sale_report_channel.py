# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class VnopSaleReportChannel(models.Model):
    _name = 'vnop.sale.report.channel'
    _description = 'Báo cáo doanh thu theo kênh/NV/nhóm SP'
    _auto = False
    _order = 'date_order desc'

    order_id = fields.Many2one('sale.order', string='Đơn hàng', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Khách hàng', readonly=True)
    user_id = fields.Many2one('res.users', string='Nhân viên', readonly=True)
    channel_type = fields.Selection(
        selection=[('wholesale', 'Bán buôn'), ('retail', 'Bán lẻ')],
        string='Kênh bán',
        readonly=True,
    )
    categ_id = fields.Many2one('product.category', string='Nhóm SP cấp 1', readonly=True)
    amount_total = fields.Monetary(string='Doanh thu', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Tiền tệ', readonly=True)
    date_order = fields.Date(string='Ngày đặt hàng', readonly=True)
    company_id = fields.Many2one('res.company', string='Công ty', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    row_number() OVER () AS id,
                    so.id AS order_id,
                    so.partner_id,
                    so.user_id,
                    so.channel_type,
                    COALESCE(pc_root.id, pc.id) AS categ_id,
                    sol.price_subtotal AS amount_total,
                    so.currency_id,
                    so.date_order::date AS date_order,
                    so.company_id
                FROM sale_order so
                JOIN sale_order_line sol ON sol.order_id = so.id
                JOIN product_product pp ON pp.id = sol.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN product_category pc ON pc.id = pt.categ_id
                LEFT JOIN product_category pc_root ON pc_root.id = pc.parent_id
                WHERE so.state IN ('sale', 'done')
            )
        """)
