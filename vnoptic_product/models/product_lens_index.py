from odoo import models, fields


class ProductLensIndex(models.Model):
    _name = 'product.lens.index'
    _description = 'Lens Index'
    _order = 'name'

    name = fields.Char('Index Name', required=True, size=50)
    description = fields.Text('Description', size=100)
    cid = fields.Char('Index Code', size=50)
    active = fields.Boolean('Active', default=True)
