# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    purchaser_id = fields.Many2one(
        comodel_name='res.partner',
        string='Đại diện mua hàng',
        help='Người liên hệ của đại lý phụ trách bảng giá này.',
    )
