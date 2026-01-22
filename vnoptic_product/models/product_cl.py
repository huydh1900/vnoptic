from odoo import models, fields


class ProductCl(models.Model):
    _name = 'product.cl'
    _description = 'Color/Lens Type'
    _order = 'name'

    name = fields.Char('CL Name', required=True, size=50)
    description = fields.Text('Description', size=100)
    cid = fields.Char('CL Code', size=50)
    active = fields.Boolean('Active', default=True)
