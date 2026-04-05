# -*- coding: utf-8 -*-

from odoo import fields, models


class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    channel_type = fields.Selection(
        selection=[
            ('all', 'Tất cả'),
            ('wholesale', 'Bán buôn'),
            ('retail', 'Bán lẻ'),
        ],
        string='Kênh áp dụng',
        default='all',
        required=True,
        help='Chương trình chỉ áp dụng cho đơn hàng thuộc kênh này. '
             'Chọn "Tất cả" để áp dụng cho mọi đơn.',
    )
