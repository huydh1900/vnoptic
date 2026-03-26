from odoo import models, fields

class ProductDesign(models.Model):
    _name = 'product.design'
    _description = 'Thiết kế phụ kiện'
    name = fields.Char('Tên thiết kế', required=True)
    code = fields.Char('Mã thiết kế')
    cid = fields.Char('Mã đồng bộ', index=True)
    active = fields.Boolean(default=True)
