from odoo import models, fields


class ProductGroupType(models.Model):
    _name = 'product.group.type'
    _description = 'Product Group Type'
    _order = 'name'

    name = fields.Char('Group Type Name', required=True)
    description = fields.Text('Description', size=200)
    activated = fields.Boolean('Activated', default=True)
