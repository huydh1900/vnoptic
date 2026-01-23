from odoo import models, fields


class ProductVe(models.Model):
    _name = 'product.ve'
    _description = 'VE (Front Part)'
    _order = 'name'

    name = fields.Char('VE Name', required=True, size=50)
    cid = fields.Char('VE Code', size=50)
    description = fields.Text('Description')
    active = fields.Boolean('Active', default=True)
