# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductLens(models.Model):
    _name = 'product.lens'
    _description = 'Lens Product Details'

    product_tmpl_id = fields.Many2one('product.template', string='Product Template')
    product_id = fields.Many2one('product.product', string='Product')

    # Optical specifications
    prism = fields.Char('Prism', size=50)
    base = fields.Char('Base', size=50)
    axis = fields.Char('Axis', size=50)
    sph = fields.Char('SPH', size=50)
    cyl = fields.Char('CYL', size=50)
    len_add = fields.Char('Lens Add', size=50)
    diameter = fields.Char('Diameter', size=50)
    corridor = fields.Char('Corridor', size=50)
    abbe = fields.Char('Abbe', size=50)
    polarized = fields.Char('Polarized', size=50)
    prism_base = fields.Char('Prism Base', size=50)
    
    # Color and coating
    color_int = fields.Char('Độ đậm màu', size=50)
    mir_coating = fields.Char('Màu tráng gương', size=50)

    # Relational fields
    # Relational fields
    design1_id = fields.Many2one('product.design', string='Thiết kế 1')
    design2_id = fields.Many2one('product.design', string='Thiết kế 2')
    uv_id = fields.Many2one('product.uv', string='Chống UV')
    cl_hmc_id = fields.Many2one('product.cl', string='Màu HMC')
    cl_pho_id = fields.Many2one('product.cl', string='Màu đổi màu (Pho)')
    cl_tint_id = fields.Many2one('product.cl', string='Màu nhuộm (Tint)')
    index_id = fields.Many2one('product.lens.index', string='Chiết suất')
    material_id = fields.Many2one('product.material', string='Chất liệu')

    coating_ids = fields.Many2many(
        'product.coating', 'lens_coating_rel',
        'lens_id', 'coating_id', 'Lớp phủ'
    )
