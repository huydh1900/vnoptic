# -*- coding: utf-8 -*-

from odoo import _, api, models, fields
from odoo.exceptions import UserError, ValidationError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.constrains('default_code')
    def _check_default_code_unique(self):
        for rec in self:
            if not rec.default_code:
                continue
            domain = [
                ('default_code', '=', rec.default_code),
                ('id', '!=', rec.id),
            ]
            if self.search_count(domain):
                raise ValidationError('Mã sản phẩm đã tồn tại!')

