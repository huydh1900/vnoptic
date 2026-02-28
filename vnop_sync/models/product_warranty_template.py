# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductWarrantyTemplate(models.Model):
    """Chính sách bảo hành chuẩn – dùng chung cho nhiều sản phẩm."""
    _name = 'product.warranty.template'
    _description = 'Chính sách bảo hành sản phẩm'
    _order = 'name'

    name = fields.Char('Tên chính sách', required=True)
    manufacturer_months = fields.Integer(
        'Bảo hành NSX (tháng)',
        default=0,
        help='Số tháng bảo hành do nhà sản xuất cung cấp'
    )
    company_months = fields.Integer(
        'Bảo hành công ty (tháng)',
        default=0,
        help='Số tháng bảo hành do công ty cam kết thêm'
    )
    note = fields.Text('Ghi chú')

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Tên chính sách bảo hành phải là duy nhất.'),
    ]
