from odoo import fields, models


class ProductColor(models.Model):
    _name = 'product.color'
    _description = 'Product Color'
    _order = 'name'

    name = fields.Char('Tên màu', required=True)
    code = fields.Char('Mã màu')
    active = fields.Boolean('Active', default=True)
