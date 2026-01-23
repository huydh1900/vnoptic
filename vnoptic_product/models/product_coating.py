from odoo import models, fields


class ProductCoating(models.Model):
    _name = 'product.coating'
    _description = 'Product Coating'
    _order = 'name'

    name = fields.Char('Coating Name', required=True, size=50)
    description = fields.Text('Description', size=100)
    cid = fields.Char('Coating Code', size=50)
    active = fields.Boolean('Active', default=True)
