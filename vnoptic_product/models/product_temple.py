from odoo import models, fields


class ProductTemple(models.Model):
    _name = 'product.temple'
    _description = 'Temple'
    _order = 'name'

    name = fields.Char('Temple Name', required=True, size=50)
    cid = fields.Char('Temple Code', size=50)
    description = fields.Text('Description')
    active = fields.Boolean('Active', default=True)
