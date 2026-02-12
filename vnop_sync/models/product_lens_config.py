# -*- coding: utf-8 -*-
from odoo import models, fields, api

class LensPower(models.Model):
    _name = 'product.lens.power'
    _description = 'Lens Power Value (SPH/CYL)'
    _order = 'value, id'

    name = fields.Char('Display Value', required=True, translate=False)
    value = fields.Float('Numeric Value', required=True, digits=(4, 2))
    type = fields.Selection([
        ('sph', 'SPH'),
        ('cyl', 'CYL')
    ], string='Type', required=True, index=True)
    active = fields.Boolean('Active', default=True)

    _sql_constraints = [
        ('value_type_uniq', 'unique (value, type)', 'The power value must be unique per type!')
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
    active = fields.Boolean('Active', default=True)

class LensMaterial(models.Model):
    _name = 'product.lens.material'
    _description = 'Lens Material'
    _order = 'refractive_index, name'

    name = fields.Char('Material Name', required=True, translate=True)
    refractive_index = fields.Float('Refractive Index', digits=(3, 3))
    description = fields.Text('Description')
    active = fields.Boolean('Active', default=True)

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
    active = fields.Boolean('Active', default=True)
