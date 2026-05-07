# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    channel_type = fields.Selection(
        selection=[
            ('wholesale', 'Bán buôn'),
            ('retail', 'Bán lẻ'),
        ],
        string='Kênh bán',
        help='Bảng giá áp dụng cho kênh này. Để trống nếu dùng cho cả hai kênh.',
    )

    purchaser_id = fields.Many2one(
        comodel_name='res.partner',
        string='Đại diện mua hàng',
        domain=[('channel_type', '=', 'wholesale')],
        help='Người liên hệ của đại lý phụ trách bảng giá này.',
    )
