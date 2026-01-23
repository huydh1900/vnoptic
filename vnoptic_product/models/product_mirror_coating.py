from odoo import models, fields


class ProductMirrorCoating(models.Model):
    _name = 'product.mirror.coating'
    _description = 'Mirror Coating (Màu tráng gương)'
    _order = 'name'

    name = fields.Char('Tên màu tráng gương', required=True, size=50)
    description = fields.Text('Mô tả', size=100)
    cid = fields.Char('Mã màu tráng gương', size=50)
    active = fields.Boolean('Active', default=True)
