# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplateIntegrationProfile(models.Model):
    _name = 'product.template.integration.profile'
    _description = 'Product Template Integration Profile'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        required=True,
        ondelete='cascade',
        index=True,
    )
    java_qr_url = fields.Char('QR URL (Java)')
    currency_zone_code = fields.Char('Mã vùng tiền tệ')
    currency_zone_value = fields.Float('Tỷ giá', digits=(12, 2))
    group_type_name = fields.Char('Loại nhóm (từ API)')
    lens_template_key = fields.Char('Lens Template Key', index=True)

    _sql_constraints = [
        ('uniq_product_template_integration_profile', 'unique(product_tmpl_id)',
         'Mỗi sản phẩm chỉ có 1 integration profile.')
    ]


class ProductTemplateLensProfile(models.Model):
    _name = 'product.template.lens.profile'
    _description = 'Product Template Lens Profile'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        required=True,
        ondelete='cascade',
        index=True,
    )

    sph_id = fields.Many2one('product.lens.power', string='SPH')
    cyl_id = fields.Many2one('product.lens.power', string='CYL')
    add_id = fields.Many2one('product.lens.power', string='ADD')
    base_curve = fields.Float('Base Curve', digits=(4, 2))
    design1_id = fields.Many2one('product.design', string='Thiết kế 1')
    design2_id = fields.Many2one('product.design', string='Thiết kế 2')
    material_id = fields.Many2one('product.lens.material', string='Vật liệu')
    index_id = fields.Many2one('product.lens.index', string='Chiết suất')
    uv_id = fields.Many2one('product.uv', string='UV')
    color_int = fields.Char('Độ đậm màu', size=50)
    coating_ids = fields.Many2many(
        'product.coating', 'product_tmpl_lens_profile_coating_rel',
        'profile_id', 'coating_id', string='Coating'
    )
    cl_hmc_id = fields.Many2one('product.cl', string='Màu HMC')
    cl_pho_id = fields.Many2one('product.cl', string='Màu Photochromic')
    cl_tint_id = fields.Many2one('product.cl', string='Màu Tinted')

    x_sph = fields.Float('SPH', digits=(6, 2))
    x_cyl = fields.Float('CYL', digits=(6, 2))
    x_add = fields.Float('ADD', digits=(6, 2))
    x_axis = fields.Integer('Axis')
    x_prism = fields.Char('Lăng kính', size=50)
    x_prism_base = fields.Char('Đáy lăng kính', size=50)
    x_hmc = fields.Char('HMC (legacy)')
    x_photochromic = fields.Char('Photochromic (legacy)')
    x_tinted = fields.Char('Tinted (legacy)')
    x_mir_coating = fields.Char('Màu tráng gương')
    x_diameter = fields.Float('Đường kính (mm)', digits=(6, 1))

    _sql_constraints = [
        ('uniq_product_template_lens_profile', 'unique(product_tmpl_id)',
         'Mỗi sản phẩm chỉ có 1 lens profile.')
    ]


class ProductTemplateOptProfile(models.Model):
    _name = 'product.template.opt.profile'
    _description = 'Product Template Optical Profile'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        required=True,
        ondelete='cascade',
        index=True,
    )

    season = fields.Char('Season', size=50)
    model = fields.Char('Model', size=50)
    serial = fields.Char('Serial', size=50)
    oem_ncc = fields.Char('OEM NCC', size=50)
    sku = fields.Char('SKU', size=50)
    color = fields.Char('Màu sắc', size=50)
    gender = fields.Selection([
        ('0', ''),
        ('1', 'Nam'),
        ('2', 'Nữ'),
        ('3', 'Unisex')
    ], string='Giới tính')

    temple_width = fields.Integer('Chiều dài càng (mm)')
    lens_width = fields.Integer('Chiều rộng tròng (mm)')
    lens_span = fields.Integer('Khoảng cách tròng (mm)')
    lens_height = fields.Integer('Chiều cao tròng (mm)')
    bridge_width = fields.Integer('Cầu mũi (mm)')

    color_front_id = fields.Many2one('product.cl', string='Màu mặt trước')
    color_temple_id = fields.Many2one('product.cl', string='Màu càng kính')
    color_lens_id = fields.Many2one('product.cl', string='Màu mắt kính')
    color_front_ids = fields.Many2many(
        'product.cl', 'product_tmpl_opt_profile_color_front_rel',
        'profile_id', 'cl_id', string='Màu mặt trước (M2M)'
    )
    color_temple_ids = fields.Many2many(
        'product.cl', 'product_tmpl_opt_profile_color_temple_rel',
        'profile_id', 'cl_id', string='Màu càng kính (M2M)'
    )

    frame_id = fields.Many2one('product.frame', string='Loại gọng')
    frame_type_id = fields.Many2one('product.frame.type', string='Kiểu gọng')
    shape_id = fields.Many2one('product.shape', string='Dáng gọng')
    ve_id = fields.Many2one('product.ve', string='Ve')
    temple_id = fields.Many2one('product.temple', string='Càng kính')
    material_ve_id = fields.Many2one('product.material', string='Chất liệu ve')
    material_temple_tip_id = fields.Many2one('product.material', string='Chất liệu chuôi càng')
    material_lens_id = fields.Many2one('product.material', string='Chất liệu mắt')
    materials_front_ids = fields.Many2many(
        'product.material', 'product_tmpl_opt_profile_material_front_rel',
        'profile_id', 'material_id', string='Chất liệu mặt trước'
    )
    materials_temple_ids = fields.Many2many(
        'product.material', 'product_tmpl_opt_profile_material_temple_rel',
        'profile_id', 'material_id', string='Chất liệu càng'
    )
    coating_ids = fields.Many2many(
        'product.coating', 'product_tmpl_opt_profile_coating_rel',
        'profile_id', 'coating_id', string='Lớp phủ'
    )

    dai_mat = fields.Float('Dài mắt (mm)', digits=(6, 2))
    ngang_mat = fields.Float('Ngang mắt (mm)', digits=(6, 2))

    _sql_constraints = [
        ('uniq_product_template_opt_profile', 'unique(product_tmpl_id)',
         'Mỗi sản phẩm chỉ có 1 optical profile.')
    ]


class ProductTemplateAccessoryProfile(models.Model):
    _name = 'product.template.accessory.profile'
    _description = 'Product Template Accessory Profile'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        required=True,
        ondelete='cascade',
        index=True,
    )

    design_id = fields.Many2one('product.design', string='Thiết kế')
    shape_id = fields.Many2one('product.shape', string='Hình dáng')
    material_id = fields.Many2one('product.material', string='Chất liệu')
    color_id = fields.Many2one('product.color', string='Màu sắc')
    width = fields.Float('Chiều rộng')
    length = fields.Float('Chiều dài')
    height = fields.Float('Chiều cao')
    head = fields.Float('Đầu')
    body = fields.Float('Thân')

    has_box = fields.Boolean('Có hộp', default=False)
    has_cleaning_cloth = fields.Boolean('Có khăn lau', default=False)
    has_warranty_card = fields.Boolean('Có thẻ bảo hành', default=False)
    note = fields.Text('Ghi chú phụ kiện')

    _sql_constraints = [
        ('uniq_product_template_accessory_profile', 'unique(product_tmpl_id)',
         'Mỗi sản phẩm chỉ có 1 accessory profile.')
    ]
