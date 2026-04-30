from odoo import models, fields


class ProductBrand(models.Model):
    _name = 'product.brand'
    _description = 'Thương hiệu'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char('Tên thương hiệu', required=True, index=True)
    code = fields.Char('CID')

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Brand name must be unique!'),
    ]
