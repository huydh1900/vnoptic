from odoo import models, fields


class ProductWarranty(models.Model):
    _name = 'product.warranty'
    _description = 'Product Warranty'
    _order = 'name'

    name = fields.Char('Warranty Name', required=True, size=50)
    description = fields.Text('Description', size=100)
    cid = fields.Char('Warranty Code', size=50)
    value = fields.Integer('Warranty Value')
    warranty_type = fields.Selection([
        ('month', 'Month'),
        ('year', 'Year'),
        ('day', 'Day')
    ], string='Warranty Type')
    active = fields.Boolean('Active', default=True)
