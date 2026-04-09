# -*- coding: utf-8 -*-
from odoo import models, fields, api

class LensPower(models.Model):
    _name = 'product.lens.power'
    _description = 'Lens Power Value (SPH/CYL)'
    _order = 'power_type, value, id'

    value = fields.Float('Giá trị', required=True, digits=(4, 2))
    power_type = fields.Selection(
        [('sph', 'SPH'), ('cyl', 'CYL')],
        string='Loại độ',
        index=True,
        help='Phân loại độ: SPH (độ cận) hoặc CYL (độ loạn). '
             'Bỏ trống cho ADD hoặc dữ liệu legacy.',
    )
    name = fields.Char(compute='_compute_name', store=True)

    @api.depends('value')
    def _compute_name(self):
        for r in self:
            r.name = "0.00" if r.value == 0.0 else f"{r.value:+.2f}"

    _sql_constraints = [
        (
            'value_type_uniq',
            'unique (value, power_type)',
            'Mỗi cặp (giá trị, loại độ) phải là duy nhất!',
        ),
    ]

class LensAdd(models.Model):
    """Giá trị ADD (Addition Power) cho tròng đa tròng / hai tròng.

    Tách riêng khỏi `product.lens.power` vì ADD chỉ là số dương (thường
    0.00 → +3.50), còn SPH/CYL thường âm. Việc tách model giúp semantic
    rõ ràng và tránh lẫn master data.
    """
    _name = 'product.lens.add'
    _description = 'Lens Addition Power (ADD)'
    _order = 'value, id'

    value = fields.Float('Giá trị', required=True, digits=(4, 2))
    name = fields.Char(compute='_compute_name', store=True)

    @api.depends('value')
    def _compute_name(self):
        for r in self:
            r.name = "0.00" if r.value == 0.0 else f"{r.value:+.2f}"

    _sql_constraints = [
        ('value_uniq', 'unique (value)', 'Giá trị ADD phải là duy nhất!'),
    ]


class LensDesign(models.Model):
    _name = 'product.lens.design'
    _description = 'Lens Design Type'
    _order = 'name'

    name = fields.Char('Design Name', required=True, translate=True)
    code = fields.Char('Code', index=True)
    design_type = fields.Selection([
        ('single', 'Single Vision'),
        ('progressive', 'Progressive'),
        ('bifocal', 'Bifocal'),
        ('other', 'Other')
    ], string='Type', required=True, default='single')

class LensMaterial(models.Model):
    _name = 'product.lens.material'
    _description = 'Lens Material'
    _order = 'refractive_index, name'

    name = fields.Char('Material Name', required=True, translate=True)
    code = fields.Char('Mã vật liệu', index=True)
    refractive_index = fields.Float('Refractive Index', digits=(3, 3))
    description = fields.Text('Description')

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
