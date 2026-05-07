# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_optical_lens = fields.Boolean(
        string='Tròng kính (cần đơn Rx)',
        default=False,
        help='Khi đánh dấu, POS sẽ tự mở popup nhập đơn kính (Rx) '
             'mỗi khi thêm sản phẩm này vào giỏ.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        if not self.env.context.get('vnop_skip_pos_category_sync'):
            products.env['product.category']._vnop_sync_pos_categories_from_products()
        return products

    def write(self, vals):
        res = super().write(vals)
        sync_fields = {'available_in_pos', 'sale_ok', 'active', 'categ_id'}
        if sync_fields.intersection(vals) and not self.env.context.get('vnop_skip_pos_category_sync'):
            self.env['product.category']._vnop_sync_pos_categories_from_products()
        return res
