from odoo import models, fields


class ProductFrameType(models.Model):
    _name = 'product.frame.type'
    _description = 'Frame Type'
    _order = 'name'

    name = fields.Char('Frame Type Name', required=True, size=50)
    cid = fields.Char('Frame Type Code', size=50)
    description = fields.Text('Description')
    active = fields.Boolean('Active', default=True)
