from odoo import models, fields

class ProductShape(models.Model):
    _name = 'product.shape'
    _description = 'Hình dáng phụ kiện'
    name = fields.Char('Tên hình dáng', required=True)
    code = fields.Char('Mã hình dáng')
    cid = fields.Char('Mã đồng bộ', index=True)
    active = fields.Boolean(default=True)
