# -*- coding: utf-8 -*-
from odoo import models, fields


class LensDesign(models.Model):
    _name = 'product.lens.design'
    _description = 'Thiết kế tròng kính'
    _order = 'name'

    name = fields.Char('Tên thiết kế', required=True, translate=True)
    name_en = fields.Char('Tên tiếng Anh')
    code = fields.Char('Viết tắt', index=True)
    design_type = fields.Selection([
        ('single', 'Đơn tròng'),
        ('progressive', 'Đa tròng'),
        ('bifocal', 'Hai tròng'),
        ('other', 'Khác'),
    ], string='Loại thiết kế', required=True, default='single')

class LensMaterial(models.Model):
    _name = 'product.lens.material'
    _description = 'Vật liệu tròng kính'
    _order = 'refractive_index, name'

    name = fields.Char('Tên vật liệu', required=True, translate=True)
    name_en = fields.Char('Tên tiếng Anh')
    code = fields.Char('Viết tắt', index=True)
    refractive_index = fields.Float('Chiết suất', digits=(3, 3))

class LensFeature(models.Model):
    _name = 'product.lens.feature'
    _description = 'Tính năng tròng kính'
    _order = 'feature_type, name'

    name = fields.Char('Tên tính năng', required=True, translate=True)
    feature_type = fields.Selection([
        ('uv', 'Chống tia UV'),
        ('hmc', 'Lớp phủ HMC'),
        ('coating', 'Lớp phủ khác'),
        ('mirror', 'Tráng gương'),
        ('tint', 'Có thể nhuộm màu'),
        ('photochromic', 'Đổi màu'),
        ('blue', 'Chống ánh sáng xanh'),
        ('other', 'Khác'),
    ], string='Loại tính năng', required=True, index=True)
    price_extra = fields.Float('Giá cộng thêm', default=0.0)
