# -*- coding: utf-8 -*-
from odoo import fields, models


class VnopReturnDefectGroup(models.Model):
    _name = 'vnop.return.defect.group'
    _description = 'Nhóm lỗi trả hàng'
    _order = 'sequence, name'

    name = fields.Char(string='Tên nhóm lỗi', required=True, translate=True)
    code = fields.Char(string='Mã', required=True)
    sequence = fields.Integer(string='Thứ tự', default=10)
    return_type = fields.Selection(
        [('policy', 'Trả hàng theo chính sách'),
         ('exception', 'Trả hàng ngoại lệ')],
        string='Loại trả', required=True,
        help='Nhóm lỗi này chỉ áp dụng cho loại trả tương ứng.')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Mã nhóm lỗi phải duy nhất.'),
    ]
