# -*- coding: utf-8 -*-
from odoo import models, fields


class LensDesign(models.Model):
    _name = 'product.lens.design'
    _description = 'Lens Design Type'
    _order = 'name'

    name = fields.Char('Design Name', required=True, translate=True)
    name_en = fields.Char('Tên tiếng Anh')
    code = fields.Char('Viết tắt', index=True)
    design_type = fields.Selection([
        ('single', 'Single Vision'),
        ('progressive', 'Progressive'),
        ('bifocal', 'Bifocal'),
        ('other', 'Other')
    ], string='Type', required=True, default='single')

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
    _description = 'Lens Feature (Coating, Tint, etc.)'
    _order = 'feature_type, name'

    name = fields.Char('Feature Name', required=True, translate=True)
    feature_type = fields.Selection([
        ('uv', 'UV Protection'),
        ('hmc', 'HMC Coating'),
        ('coating', 'Other Coating'),
        ('mirror', 'Mirror Coating'),
        ('tint', 'Can Tint'),
        ('photochromic', 'Photochromic'),
        ('blue', 'Blue Control'),
        ('other', 'Other')
    ], string='Feature Type', required=True, index=True)
    price_extra = fields.Float('Price Extra', default=0.0)
