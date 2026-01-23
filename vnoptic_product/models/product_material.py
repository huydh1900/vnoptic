from odoo import models, fields


class ProductMaterial(models.Model):
    _name = 'product.material'
    _description = 'Product Material'
    _order = 'name'

    name = fields.Char('Material Name', required=True, size=50)
    description = fields.Text('Description', size=100)
    cid = fields.Char('Material Code', size=50)
    active = fields.Boolean('Active', default=True)
