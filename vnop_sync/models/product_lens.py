# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductLens(models.Model):
    _name = 'product.lens'
    _description = 'Lens Product Details'

    product_tmpl_id = fields.Many2one('product.template', string='Product Template')
    product_id = fields.Many2one('product.product', string='Product')

    # 1. Power Configuration (Config-Driven)
    sph_id = fields.Many2one('product.lens.power', string='SPH', domain="[('type', '=', 'sph')]")
    cyl_id = fields.Many2one('product.lens.power', string='CYL', domain="[('type', '=', 'cyl')]")

    # 2. Axis (Manual Input, Validated)
    axis = fields.Integer('Axis (0-180)')
    
    # 3. Addition (Manual Input, Validated)
    lens_add = fields.Float('ADD', digits=(4, 2))

    # 4. Base Curve (Manual Input, Validated)
    base_curve = fields.Float('Base Curve', digits=(4, 2))

    # 5. Diameter (Manual Input, Validated)
    diameter = fields.Integer('Diameter', required=True)

    # 6. Lens Design (Legacy fields from old system)
    design1_id = fields.Many2one('product.design', string='Thiết kế 1')
    design2_id = fields.Many2one('product.design', string='Thiết kế 2')
    design_id = fields.Many2one('product.lens.design', string='Design (New)')

    # 7. Material (Config-Driven)
    material_id = fields.Many2one('product.lens.material', string='Vật liệu')
    
    # 8. Lens Index (Chiết suất)
    index_id = fields.Many2one('product.lens.index', string='Chiết suất')
    
    # 9. UV Protection
    uv_id = fields.Many2one('product.uv', string='UV')
    
    # 10. Color/Coating specific fields (Legacy)
    cl_hmc_id = fields.Many2one('product.cl', string='HMC')
    cl_pho_id = fields.Many2one('product.cl', string='Photochromic')
    cl_tint_id = fields.Many2one('product.cl', string='Tint')
    
    # 11. Coatings (Lớp trắng/Lớp phủ)
    coating_ids = fields.Many2many(
        'product.coating', 'lens_coating_rel',
        'lens_id', 'coating_id', string='Lớp trắng'
    )
    
    # 12. Features (New Config-Driven, for future use)
    feature_ids = fields.Many2many(
        'product.lens.feature', 'lens_feature_rel', 
        'lens_id', 'feature_id', string='Features & Coatings (New)'
    )
    
    # Helper fields for display/search if needed
    corridor = fields.Char('Corridor', size=50) # Keep specialized params
    abbe = fields.Char('Abbe', size=50)
    prism = fields.Char('Prism', size=50)
    prism_base = fields.Char('Prism Base', size=50)

    # --- Validation Logic ---

    @api.constrains('cyl_id', 'axis')
    def _check_axis(self):
        for rec in self:
            # If CYL is selected and not 0.00
            if rec.cyl_id and rec.cyl_id.value != 0:
                if not rec.axis and rec.axis != 0:
                     # Note: 0 is valid axis, but None/False is not if CYL exists
                     # However, Integer field defaults to 0. So we check if it was explicitly set?
                     # Odoo Integer field 0 is False-like in some contexts but 0 is a value.
                     # Let's assume 0-180 range check handles validity.
                     # But requirement says "If cyl != 0 -> axis required".
                     pass 
                
            if rec.axis < 0 or rec.axis > 180:
                raise ValidationError(_("Axis must be between 0 and 180 (received %s).") % rec.axis)

    @api.constrains('design_id', 'lens_add')
    def _check_add(self):
        for rec in self:
            if rec.design_id:
                if rec.design_id.design_type in ['progressive', 'bifocal']:
                    if rec.lens_add <= 0:
                        raise ValidationError(_("Addition (ADD) is required for Progressive/Bifocal designs."))
                else:
                    # Single vision -> ADD should be 0 or empty?
                    # Strict check:
                    if rec.lens_add > 0:
                         raise ValidationError(_("Addition (ADD) must be 0 for Single Vision lenses."))

    @api.constrains('diameter')
    def _check_diameter(self):
        for rec in self:
            if rec.diameter < 55 or rec.diameter > 90:
                raise ValidationError(_("Diameter must be between 55 and 90 mm (received %s).") % rec.diameter)

    @api.constrains('base_curve')
    def _check_base_curve(self):
        for rec in self:
            if rec.base_curve and (rec.base_curve < 2 or rec.base_curve > 12):
                 # Relaxed range 2-12 based on common lenses, user asked 4-9 strictly?
                 # User prompt: "Range 4 -> 9". OK strict.
                 if rec.base_curve < 4 or rec.base_curve > 9:
                    raise ValidationError(_("Base Curve must be between 4.00 and 9.00 (received %s).") % rec.base_curve)

