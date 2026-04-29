from odoo import models, fields

class ProductShape(models.Model):
    _name = 'product.shape'
    _description = 'Hình dáng'
    _order = 'name'

    name = fields.Char('Dáng', required=True)
    cid = fields.Char('Viết tắt', index=True)
