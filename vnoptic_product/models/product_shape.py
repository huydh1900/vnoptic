from odoo import models, fields


class ProductShape(models.Model):
    _name = 'product.shape'
    _description = 'Shape'
    _order = 'name'

    name = fields.Char('Shape Name', required=True, size=50)
    cid = fields.Char('Shape Code', required=True, size=50)
    description = fields.Text('Description')
    active = fields.Boolean('Active', default=True)
