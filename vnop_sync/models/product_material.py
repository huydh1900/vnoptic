from odoo import models, fields

class ProductMaterial(models.Model):
    _name = 'product.material'
    _description = 'Chất liệu'
    _order = 'name'
    name = fields.Char('Tên chất liệu', required=True)
    code = fields.Char('Mã chất liệu')
    cid = fields.Char('Mã đồng bộ', index=True)
    description = fields.Text('Mô tả')
