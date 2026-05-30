# -*- coding: utf-8 -*-
from odoo import fields, models


class VnopReturnReason(models.Model):
    _name = 'vnop.return.reason'
    _description = 'Lý do trả hàng'
    _order = 'defect_group, sequence, name'

    name = fields.Char(string='Tên lý do', required=True, translate=True)
    code = fields.Char(string='Mã', required=True)
    sequence = fields.Integer(string='Thứ tự', default=10)
    defect_group = fields.Many2one(
        'vnop.return.defect.group', string='Nhóm lỗi',
        required=True, ondelete='restrict')
    default_return_type = fields.Selection(
        [
            ('policy', 'Trả hàng theo chính sách'),
            ('exception', 'Trả hàng ngoại lệ'),
        ],
        string='Loại trả mặc định',
        required=True,
        default='policy',
        help='Khi Sale chọn lý do này, hệ thống tự đề xuất loại trả tương ứng.',
    )
    description = fields.Text(string='Mô tả', translate=True,
                              help='Hiển thị tooltip cho Sale khi chọn lý do.')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Mã lý do trả hàng phải duy nhất.'),
    ]
