from odoo import models, fields


class ProductGroup(models.Model):
    _name = 'product.group'
    _description = 'Product Group'
    _order = 'name'

    name = fields.Char('Tên nhóm', required=True)
    description = fields.Text('Mô tả', size=200)
    activated = fields.Boolean('Kích hoạt', default=True)
    cid = fields.Char("Mã nhóm", required=True)
    group_type_id = fields.Many2one('product.group.type', string='Loại nhóm')
