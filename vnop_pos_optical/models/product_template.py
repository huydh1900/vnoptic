# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_optical_lens = fields.Boolean(
        string='Tròng kính (cần đơn Rx)',
        default=False,
        help='Khi đánh dấu, POS sẽ tự mở popup nhập đơn kính (Rx) '
             'mỗi khi thêm sản phẩm này vào giỏ.',
    )
