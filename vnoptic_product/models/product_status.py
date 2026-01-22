from odoo import models, fields


class ProductStatus(models.Model):
    _name = 'product.status'
    _description = 'Product Status'
    _order = 'name'

    name = fields.Char('Status Name', required=True)
    description = fields.Text('Description')
    activated = fields.Boolean('Activated', default=True)
