from odoo import models, fields


class ProductWarranty(models.Model):
    _name = 'product.warranty'
    _description = 'Bảo hành (XNK)'
    _order = 'code, name'
    _rec_name = 'name'

    name = fields.Char('Tên bảo hành', required=True, index=True)
    code = fields.Char('Mã bảo hành', required=True, index=True)
    description = fields.Text('Mô tả')

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Warranty code must be unique!'),
    ]

    def name_get(self):
        return [(record.id, record.name) for record in self]
