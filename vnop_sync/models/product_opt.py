# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductOpt(models.Model):
    _name = 'product.opt'
    _description = 'Optical Product Details'

    product_tmpl_id = fields.Many2one('product.template', 'Product Template')
    product_id = fields.Many2one('product.product', 'Product Variant')


    season = fields.Char('Season', size=50)
    model = fields.Char('Model', size=50)
    serial = fields.Char('Serial', size=50)
    oem_ncc = fields.Char('OEM Supplier', size=50)
    sku = fields.Char('SKU', size=50)
    gender = fields.Selection([
        ('1', 'Male'),
        ('2', 'Female'),
        ('3', 'Unisex')
    ], 'Gender')

    # Dimensions
    temple_width = fields.Integer('Temple Width')
    lens_width = fields.Integer('Lens Width')
    lens_span = fields.Integer('Lens Span')
    lens_height = fields.Integer('Lens Height')
    bridge_width = fields.Integer('Bridge Width')

    # Colors
    color = fields.Char('Color', size=50)
    color_front_id = fields.Many2one('product.cl', 'Màu mặt trước')
    color_temple_id = fields.Many2one('product.cl', 'Màu càng')
    color_lens_id = fields.Many2one('product.cl', 'Màu mắt kính')

    # Design fields
    frame_id = fields.Many2one('product.frame', 'Kiểu gọng')
    frame_type_id = fields.Many2one('product.frame.type', 'Loại gọng')
    shape_id = fields.Many2one('product.shape', 'Dáng')
    ve_id = fields.Many2one('product.ve', 'Ve')
    temple_id = fields.Many2one('product.temple', 'Càng kính')
    
    # Material fields
    material_ve_id = fields.Many2one('product.material', 'Chất liệu ve')
    material_temple_tip_id = fields.Many2one('product.material', 'Chất liệu chuôi càng')
    material_lens_id = fields.Many2one('product.material', 'Chất liệu mắt')

    # Many2many
    coating_ids = fields.Many2many(
        'product.coating', 'opt_coating_rel',
        'opt_id', 'coating_id', 'Lớp phủ'
    )
    materials_front_ids = fields.Many2many(
        'product.material', 'opt_material_front_rel',
        'opt_id', 'material_id', 'Chất liệu mặt trước'
    )
    materials_temple_ids = fields.Many2many(
        'product.material', 'opt_material_temple_rel',
        'opt_id', 'material_id', 'Chất liệu càng'
    )
