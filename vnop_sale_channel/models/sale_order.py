# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    channel_type = fields.Selection(
        selection=[
            ('wholesale', 'Bán buôn'),
            ('retail', 'Bán lẻ'),
        ],
        string='Kênh bán',
        compute='_compute_channel_type',
        store=True,
        readonly=False,
        precompute=True,
        help='Kênh bán của đơn hàng. Mặc định lấy từ khách hàng, có thể chỉnh tay.',
    )

    @api.depends('partner_id')
    def _compute_channel_type(self):
        for order in self:
            if order.partner_id and order.partner_id.channel_type:
                order.channel_type = order.partner_id.channel_type
            elif not order.channel_type:
                order.channel_type = 'retail'

    @api.depends('channel_type')
    def _compute_pricelist_id(self):
        """Khi chọn kênh bán, tự động gán bảng giá khớp channel_type tương ứng.

        - Giữ bảng giá hiện tại nếu đã khớp kênh (hoặc bảng giá 'chung' - channel_type=False).
        - Ưu tiên bảng giá cùng kênh; nếu không có thì fallback logic gốc (theo partner).
        """
        super()._compute_pricelist_id()
        for order in self:
            if order.state != 'draft' or not order.channel_type:
                continue
            if order.pricelist_id and order.pricelist_id.channel_type in (order.channel_type, False):
                continue
            matching = self.env['product.pricelist'].search([
                ('channel_type', '=', order.channel_type),
                ('company_id', 'in', (False, order.company_id.id)),
            ], limit=1)
            if matching:
                order.pricelist_id = matching
