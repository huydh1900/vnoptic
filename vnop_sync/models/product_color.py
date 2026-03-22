from odoo import models, fields

class ProductColor(models.Model):
    _name = 'product.color'
    _description = 'Màu sắc phụ kiện'
    name = fields.Char('Tên màu sắc', required=True)
    code = fields.Char('Mã màu sắc')
    cid = fields.Char('Mã đồng bộ', index=True)
    active = fields.Boolean(default=True)
