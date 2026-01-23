from odoo import models, fields


class ProductColorIntensity(models.Model):
    _name = 'product.color.intensity'
    _description = 'Color Intensity (Độ đậm màu)'
    _order = 'name'

    name = fields.Char('Tên độ đậm màu', required=True, size=50)
    description = fields.Text('Mô tả', size=100)
    cid = fields.Char('Mã độ đậm màu', size=50)
    active = fields.Boolean('Active', default=True)
