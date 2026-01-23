from odoo import models, fields


class ProductUv(models.Model):
    _name = 'product.uv'
    _description = 'UV Protection'
    _order = 'name'

    name = fields.Char('UV Name', required=True, size=50)
    description = fields.Text('Description', size=50)
    cid = fields.Char('UV Code', size=50)
    active = fields.Boolean('Active', default=True)
