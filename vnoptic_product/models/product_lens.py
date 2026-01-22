from odoo import models, fields, api


class ProductLens(models.Model):
    _name = 'product.lens'
    _description = 'Lens Product'

    product_tmpl_id = fields.Many2one('product.template', string='Product Template')
    product_id = fields.Many2one('product.product', string='Product')

    prism = fields.Char('Prism', size=50)
    base = fields.Char('Base', size=50)
    axis = fields.Char('Axis', size=50)
    sph = fields.Char('Sph', size=50)
    cyl = fields.Char('Cyl', size=50)
    len_add = fields.Char('Lens Add', size=50)
    diameter = fields.Char('Diameter', size=50)
    corridor = fields.Char('Corridor', size=50)
    abbe = fields.Char('Abbe', size=50)
    polarized = fields.Char('Polarized', size=50)
    prism_base = fields.Char('Prism Base', size=50)
    
    # String fields for direct input
    color_int = fields.Char('Độ đậm màu', size=50)
    mir_coating = fields.Char('Màu tráng gương', size=50)

    design1_id = fields.Many2one('product.design', string='Design1')
    design2_id = fields.Many2one('product.design', string='Design2')
    uv_id = fields.Many2one('product.uv', string='UV')
    cl_hmc_id = fields.Many2one('product.cl', string='CL HMC')
    cl_pho_id = fields.Many2one('product.cl', string='CL Pho')
    cl_tint_id = fields.Many2one('product.cl', string='CL Tint')
    index_id = fields.Many2one('product.lens.index', string='Index')
    material_id = fields.Many2one('product.material', string='Material')

    coating_ids = fields.Many2many('product.coating', 'lens_coating_rel',
                                   'lens_id', 'coating_id', 'Coatings')

    @api.onchange('index_id')
    def _onchange_index_update_code(self):
        """Update product code when lens index changes"""
        from odoo.addons.vnoptic_product import utils as vnoptic_utils
        
        if self.product_tmpl_id and (self.product_tmpl_id.group_id or self.product_tmpl_id.brand_id or self.index_id):
            code = vnoptic_utils.product_code_utils.generate_product_code(
                self.env,
                self.product_tmpl_id.group_id.id if self.product_tmpl_id.group_id else False,
                self.product_tmpl_id.brand_id.id if self.product_tmpl_id.brand_id else False,
                self.index_id.id if self.index_id else False
            )
            self.product_tmpl_id.default_code = code
