from odoo import models, fields


class ProductOpt(models.Model):
    _name = 'product.opt'
    _description = 'Optical Product Details'

    product_tmpl_id = fields.Many2one('product.template', 'Product Template')
    product_id = fields.Many2one('product.product', 'Product Variant')

    # Thông tin sản phẩm
    season = fields.Char('Season', size=50)
    model = fields.Char('Model', size=50)
    serial = fields.Char('Serial', size=50)
    oem_ncc = fields.Char('OEM Supplier', size=50)
    sku = fields.Char('SKU', size=50)
    gender = fields.Selection([('1', 'Male'), ('2', 'Female'), ('3', 'Unisex')], 'Gender')

    temple_width = fields.Integer('Temple Width')
    lens_width = fields.Integer('Lens Width')
    lens_span = fields.Integer('Lens Span')
    lens_height = fields.Integer('Lens Height')
    bridge_width = fields.Integer('Bridge Width')

    color = fields.Char('Color', size=50)
    color_front_id = fields.Many2one('product.cl', 'Front Color')
    color_temple_id = fields.Many2one('product.cl', 'Temple Color')

    # Optical design fields - Many2one to lookup tables
    frame_id = fields.Many2one('product.frame', 'Frame')
    frame_type_id = fields.Many2one('product.frame.type', 'Frame Type')
    shape_id = fields.Many2one('product.shape', 'Shape')
    ve_id = fields.Many2one('product.ve', 'VE')
    temple_id = fields.Many2one('product.temple', 'Temple')
    
    # Material fields
    material_ve_id = fields.Many2one('product.material', 'VE Material')
    material_temple_tip_id = fields.Many2one('product.material', 'Temple Tip Material')
    material_lens_id = fields.Many2one('product.material', 'Lens Material')
    color_lens_id = fields.Many2one('product.cl', 'Lens Color')

    coating_ids = fields.Many2many('product.coating', 'opt_coating_rel',
                                   'opt_id', 'coating_id', 'Coatings')
    materials_front_ids = fields.Many2many('product.material', 'opt_material_front_rel',
                                           'opt_id', 'material_id', 'Front Materials')
    materials_temple_ids = fields.Many2many('product.material', 'opt_material_temple_rel',
                                            'opt_id', 'material_id', 'Temple Materials')
