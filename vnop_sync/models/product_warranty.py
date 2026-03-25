from odoo import models, fields


class ProductWarranty(models.Model):
    _name = 'product.warranty'
    _description = 'Bảo hành (XNK)'
    _order = 'code, name'
    _rec_name = 'name'

    # Basic Fields
    name = fields.Char('Tên bảo hành', required=True, index=True)
    code = fields.Char('Mã bảo hành', required=True, index=True)
    description = fields.Text('Mô tả')
    value = fields.Integer('Thời hạn (ngày)', default=0, help='Thời hạn bảo hành tính bằng ngày')

    # SQL Constraints
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Warranty code must be unique!'),
    ]

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, record.name))
        return result
