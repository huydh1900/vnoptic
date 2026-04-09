from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProductBrand(models.Model):
    _name = 'product.brand'
    _description = 'Thương hiệu'
    _order = 'sequence, name'
    _rec_name = 'name'

    name = fields.Char('Tên thương hiệu', required=True, index=True)
    code = fields.Char('CID')
    sequence = fields.Integer('STT', default=lambda self: (self.search([], order='sequence desc', limit=1).sequence or 0) + 1)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Brand name must be unique!'),
    ]

    @api.constrains('sequence')
    def _check_sequence_unique(self):
        for rec in self:
            if self.search_count([('sequence', '=', rec.sequence), ('id', '!=', rec.id)]):
                raise ValidationError(f'STT {rec.sequence} đã tồn tại, vui lòng chọn STT khác!')
