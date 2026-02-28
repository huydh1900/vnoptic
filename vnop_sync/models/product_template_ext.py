# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductCategory(models.Model):
    """Extend product.category to add code field for product code generation"""
    _inherit = 'product.category'
    
    code = fields.Char('Mã danh mục', size=2, index=True,
                       help='Mã 2 số dùng cho tạo mã sản phẩm (VD: 06=Tròng kính, 27=Gọng kính, 20=Phụ kiện)')


class ProductTemplateExtension(models.Model):
    _inherit = 'product.template'

    _sql_constraints = [
        ('short_code_unique', 'unique(short_code)',
         'Mã viết tắt phải là duy nhất.'),
    ]

    # Computed fields to replace product_type for UI logic
    is_lens = fields.Boolean(compute='_compute_product_kind', store=True)
    is_opt = fields.Boolean(compute='_compute_product_kind', store=True)

    @api.depends('product_type')
    def _compute_product_kind(self):
        for record in self:
            record.is_opt = record.product_type == 'opt'
            record.is_lens = record.product_type == 'lens'

    # Keep product_type for now but make it computed or optional if needed
    # For now we just add the new logic alongside
    x_eng_name = fields.Char(
        'Tên tiếng Anh',
        help="Product name in English"
    )

    x_trade_name = fields.Char(
        'Tên thương mại',
        help="Commercial trade name"
    )


    x_uses = fields.Text(
        'Công dụng',
        help="Product usage instructions"
    )

    x_guide = fields.Text(
        'Hướng dẫn sử dụng',
        help="Step-by-step usage guide"
    )

    x_warning = fields.Text(
        'Cảnh báo',
        help="Safety warnings and precautions"
    )

    x_preserve = fields.Text(
        'Bảo quản',
        help="Storage and preservation guidelines"
    )


    x_cid_ncc = fields.Char(
        'Mã NCC',
        help="Supplier product code"
    )

    x_accessory_total = fields.Integer(
        'Tổng phụ kiện',
        default=0,
        help="Number of accessories included"
    )

    # Note: Retail price uses standard Odoo field 'list_price'
    # Note: Cost price (Giá vốn) uses standard Odoo field 'standard_price'

    x_ws_price = fields.Float(
        'Giá sỉ',
        digits='Product Price',
        help="Wholesale price"
    )

    x_or_price = fields.Float(
        'Giá gốc',
        digits='Product Price',
        help="Original price from supplier"
    )

    x_ws_price_min = fields.Float(
        'Giá sỉ Min',
        digits='Product Price',
        help="Minimum wholesale price"
    )

    x_ws_price_max = fields.Float(
        'Giá sỉ Max',
        digits='Product Price',
        help="Maximum wholesale price"
    )


    x_currency_zone_code = fields.Char(
        'Mã vùng tiền tệ',
        help="Currency zone code from API"
    )

    x_currency_zone_value = fields.Float(
        'Tỷ giá',
        digits=(12, 2),
        help="Currency zone exchange rate"
    )


    x_group_type_name = fields.Char(
        'Loại nhóm (từ API)',
        help="Product group type from API - for reference only"
    )

    # ==================== PRODUCT TYPE (for sync categorization) ====================
    product_type = fields.Selection([
        ('lens', 'Tròng kính'),
        ('opt', 'Gọng kính'),
        ('accessory', 'Phụ kiện')
    ], string='Phân loại nghiệp vụ', default='lens',
       help="Phân loại sản phẩm: Tròng kính / Gọng kính / Phụ kiện"
    )

    # ==================== RELATIONAL FIELDS (for sync) ====================
    brand_id = fields.Many2one(
        'product.brand', 'Thương hiệu',
        index=True, tracking=True,
        help="Product brand"
    )
    warranty_id = fields.Many2one(
        'product.warranty', 'Bảo hành',
        help="Product warranty"
    )
    # Note: Supplier management uses standard Odoo field 'seller_ids' (One2many to product.supplierinfo)
    # This allows managing multiple suppliers with prices and conditions per supplier
    country_id = fields.Many2one(
        'product.country', 'Xuất xứ',
        help="Country of origin for the product"
    )

    # ==================== LENS/OPT RELATIONSHIPS ====================
    lens_ids = fields.One2many('product.lens', 'product_tmpl_id', 'Lens Details')
    # opt_ids giữ lại tạm để migrate dữ liệu cũ, KHÔNG dùng cho logic nghiệp vụ mới
    opt_ids = fields.One2many('product.opt', 'product_tmpl_id', 'Optical Details (Legacy)')

    # ==================== ADDITIONAL FIELDS FOR VIEW ====================
    group_id = fields.Many2one('product.group', string='Nhóm sản phẩm (theo loại)',
                                help='Nhóm sản phẩm - tự động lọc theo phân loại nghiệp vụ')
    index_id = fields.Many2one('product.lens.index', string='Chiết suất', 
                                help='Lens index for code generation (lens products only)')
    auto_generate_code = fields.Boolean('Tự động tạo mã', default=True,
                                         help='Automatically generate product code based on Group, Brand, and Index')
    status_product_id = fields.Many2one('product.status', 'Trạng thái')

    # ==================== LENS SPECS (Hướng B: field trực tiếp trên template) ====================
    # Thiết kế
    lens_sph_id = fields.Many2one('product.lens.power', string='SPH',
        domain="[('type', '=', 'sph')]",
        help='Công suất cầu (Sphere)')
    lens_cyl_id = fields.Many2one('product.lens.power', string='CYL',
        domain="[('type', '=', 'cyl')]",
        help='Công suất trụ (Cylinder)')
    lens_add = fields.Float('ADD', digits=(4, 2), help='Addition (thấu kính đa tròng)')
    lens_base_curve = fields.Float('Base Curve', digits=(4, 2))
    lens_diameter = fields.Integer('Đường kính')
    lens_prism = fields.Char('Prism', size=50)
    lens_design1_id = fields.Many2one('product.design', string='Thiết kế 1')
    lens_design2_id = fields.Many2one('product.design', string='Thiết kế 2')

    # Chất liệu
    lens_material_id = fields.Many2one('product.lens.material', string='Vật liệu')
    lens_index_id = fields.Many2one('product.lens.index', string='Chiết suất')

    # Tích hợp
    lens_uv_id = fields.Many2one('product.uv', string='UV')
    lens_cl_hmc_id = fields.Many2one('product.cl', string='HMC')
    lens_cl_pho_id = fields.Many2one('product.cl', string='Pho Col')
    lens_cl_tint_id = fields.Many2one('product.cl', string='Tint Col')
    lens_color_int = fields.Char('Độ đậm màu', size=50)
    lens_mir_coating = fields.Char('Màu tráng gương', size=50)
    lens_coating_ids = fields.Many2many(
        'product.coating',
        'product_tmpl_coating_rel', 'tmpl_id', 'coating_id',
        string='Coating'
    )

    # ==================== OPT SPECS (Hướng B: field trực tiếp trên template) ====================
    # Thông tin cơ bản
    opt_season = fields.Char('Season', size=50)
    opt_model = fields.Char('Model', size=50)
    opt_serial = fields.Char('Serial', size=50)
    opt_oem_ncc = fields.Char('OEM NCC', size=50)
    opt_sku = fields.Char('SKU', size=50)
    opt_color = fields.Char('Màu sắc', size=50)
    opt_gender = fields.Selection([
        ('1', 'Nam'), ('2', 'Nữ'), ('3', 'Unisex')
    ], string='Giới tính')

    # Kích thước
    opt_temple_width = fields.Integer('Chiều dài càng (mm)')
    opt_lens_width = fields.Integer('Chiều rộng tròng (mm)')
    opt_lens_span = fields.Integer('Khoảng cách tròng (mm)')
    opt_lens_height = fields.Integer('Chiều cao tròng (mm)')
    opt_bridge_width = fields.Integer('Cầu mũi (mm)')

    # Màu sắc
    opt_color_front_id = fields.Many2one('product.cl', string='Màu mặt trước')
    opt_color_temple_id = fields.Many2one('product.cl', string='Màu càng')
    opt_color_lens_id = fields.Many2one('product.cl', string='Màu mắt kính')

    # Thiết kế
    opt_frame_id = fields.Many2one('product.frame', string='Kiểu gọng')
    opt_frame_type_id = fields.Many2one('product.frame.type', string='Loại gọng')
    opt_shape_id = fields.Many2one('product.shape', string='Dáng gọng')
    opt_ve_id = fields.Many2one('product.ve', string='Ve')
    opt_temple_id = fields.Many2one('product.temple', string='Càng kính')

    # Chất liệu
    opt_material_ve_id = fields.Many2one('product.material', string='Chất liệu ve')
    opt_material_temple_tip_id = fields.Many2one('product.material', string='Chất liệu chuôi càng')
    opt_material_lens_id = fields.Many2one('product.material', string='Chất liệu mắt')
    opt_materials_front_ids = fields.Many2many(
        'product.material', 'product_tmpl_material_front_rel',
        'tmpl_id', 'material_id', string='Chất liệu mặt trước'
    )
    opt_materials_temple_ids = fields.Many2many(
        'product.material', 'product_tmpl_material_temple_rel',
        'tmpl_id', 'material_id', string='Chất liệu càng'
    )
    opt_coating_ids = fields.Many2many(
        'product.coating', 'product_tmpl_opt_coating_rel',
        'tmpl_id', 'coating_id', string='Lớp phủ'
    )

    # ==================== SHORT CODE ====================
    short_code = fields.Char(
        string='Mã viết tắt',
        required=True,
        index=True,
        copy=False,
        help='Mã viết tắt duy nhất cho sản phẩm gọng kính'
    )

    # ==================== WARRANTY TEMPLATE (Hướng A – ERP chuẩn) ====================
    warranty_template_id = fields.Many2one(
        'product.warranty.template',
        string='Chính sách bảo hành',
        help='Chọn chính sách bảo hành áp dụng cho sản phẩm'
    )
    manufacturer_months = fields.Integer(
        related='warranty_template_id.manufacturer_months',
        string='Bảo hành NSX (tháng)',
        readonly=True,
        store=True,
    )
    company_months = fields.Integer(
        related='warranty_template_id.company_months',
        string='Bảo hành công ty (tháng)',
        readonly=True,
        store=True,
    )

    # ==================== RS FRAME FIELDS (field mới, không trùng opt_*) ====================
    # Kích thước bổ sung
    dai_mat = fields.Float(
        'Dài mắt (mm)',
        digits=(6, 2),
        help='Chiều dài mắt kính – RS field: dai_mat'
    )
    ngang_mat = fields.Float(
        'Ngang mắt (mm)',
        digits=(6, 2),
        help='Chiều ngang mắt kính – RS field: ngang_mat'
    )
    # Giá
    gia_si_theo_phan_tram = fields.Float(
        'Giá sỉ theo % (RS)',
        digits=(6, 2),
        help='Tỷ lệ % chiết khấu sỉ – RS field: gia_si_theo_phan_tram'
    )
    # Đơn vị nguyên tệ
    don_vi_nguyen_te = fields.Many2one(
        'res.currency',
        string='Đơn vị nguyên tệ',
        help='Loại tiền tệ nhập hàng – RS field: don_vi_nguyen_te'
    )
    # Bảo hành bán lẻ
    bao_hanh_ban_le = fields.Integer(
        'Bảo hành bán lẻ (tháng)',
        default=0,
        help='Số tháng bảo hành cam kết với khách bán lẻ – RS field: bao_hanh_ban_le'
    )

    # ==================== ACCESSORIES ====================
    has_box = fields.Boolean('Có hộp', default=False)
    has_cleaning_cloth = fields.Boolean('Có khăn lau', default=False)
    has_warranty_card = fields.Boolean('Có thẻ bảo hành', default=False)
    accessory_note = fields.Text('Ghi chú phụ kiện')

    # ==================== COMPUTED FIELDS FOR TREE VIEW ====================
    # Lens display fields (computed từ field mới, dùng cho tree/search)
    lens_sph = fields.Char('SPH (hiển thị)', compute='_compute_lens_info', store=False, readonly=True)
    lens_cyl = fields.Char('CYL (hiển thị)', compute='_compute_lens_info', store=False, readonly=True)
    lens_index_name = fields.Char('Index (hiển thị)', compute='_compute_lens_info', store=False, readonly=True)

    # Opt display fields (computed từ field mới, dùng cho tree/search)
    opt_frame_type = fields.Char('Loại gọng (hiển thị)', compute='_compute_opt_info', store=False, readonly=True)
    opt_shape = fields.Char('Dáng gọng (hiển thị)', compute='_compute_opt_info', store=False, readonly=True)

    @api.depends('lens_sph_id', 'lens_cyl_id', 'lens_index_id')
    def _compute_lens_info(self):
        for record in self:
            record.lens_sph = record.lens_sph_id.name if record.lens_sph_id else ''
            record.lens_cyl = record.lens_cyl_id.name if record.lens_cyl_id else ''
            record.lens_index_name = record.lens_index_id.name if record.lens_index_id else ''
    
    @api.depends('opt_frame_type_id', 'opt_shape_id')
    def _compute_opt_info(self):
        for record in self:
            record.opt_frame_type = record.opt_frame_type_id.name if record.opt_frame_type_id else ''
            record.opt_shape = record.opt_shape_id.name if record.opt_shape_id else ''

    # ==================== COMPUTED FIELD FOR PRIMARY SUPPLIER ====================
    primary_supplier_id = fields.Many2one('res.partner', string='Nhà cung cấp chính', 
                                           compute='_compute_primary_supplier', store=False, readonly=True,
                                           help='Nhà cung cấp chính (lấy từ seller_ids đầu tiên)')
    
    @api.depends('seller_ids', 'seller_ids.partner_id')
    def _compute_primary_supplier(self):
        for record in self:
            if record.seller_ids:
                record.primary_supplier_id = record.seller_ids[0].partner_id
            else:
                record.primary_supplier_id = False

    # ==================== PRODUCT CREATION LOGIC ====================
    @api.model
    def create(self, vals):
        # Auto-generate product code if enabled and not provided
        if vals.get('auto_generate_code', True) and not vals.get('default_code'):
            categ_id = vals.get('categ_id')  # Changed from group_id
            brand_id = vals.get('brand_id')
            index_id = vals.get('index_id')  # For lens products
            
            if categ_id and brand_id:  # Changed from group_id
                from ..utils import product_code_utils
                try:
                    code = product_code_utils.generate_product_code(
                        self.env, categ_id, brand_id, index_id  # Changed from group_id
                    )
                    vals['default_code'] = code
                except Exception as e:
                    # Log error but don't fail product creation
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.warning(f"Failed to auto-generate product code: {e}")
        
        product_type = vals.get('product_type', 'lens')

        if product_type != 'lens':
            if 'lens_ids' in vals:
                del vals['lens_ids']

        if product_type != 'opt':
            if 'opt_ids' in vals:
                del vals['opt_ids']

        product = super().create(vals)
        
        # Auto-create opt record if needed (lens dùng field trực tiếp trên template - Hướng B)
        if product_type == 'opt' and not product.opt_ids:
            self.env['product.opt'].create({'product_tmpl_id': product.id})
        
        return product

    def write(self, vals):
        product_type = vals.get('product_type') or self.product_type

        if 'product_type' in vals:
            if vals['product_type'] != 'lens':
                if self.lens_ids:
                    self.lens_ids.unlink()
                if 'lens_ids' in vals:
                    del vals['lens_ids']

            if vals['product_type'] != 'opt':
                if self.opt_ids:
                    self.opt_ids.unlink()
                if 'opt_ids' in vals:
                    del vals['opt_ids']

        return super().write(vals)

    def action_create_missing_details(self):
        """Create missing opt records for products that have product_type but no details.
        Lens products use direct fields on template (Hướng B), no child records needed."""
        created_opt = 0
        
        for product in self:
            if product.product_type == 'opt' and not product.opt_ids:
                self.env['product.opt'].create({'product_tmpl_id': product.id})
                created_opt += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Đã tạo records',
                'message': f'Tạo {created_opt} opt records (lens dùng field trực tiếp trên template)',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def cron_create_all_missing_details(self):
        """Cron job to create missing lens/opt records for ALL products"""
        # Create lens records for lens products without details
        # Lens products use direct fields on template (Hướng B).
        # No auto-creation of product.lens records needed.
        
        # Create opt records for opt products without details
        opt_products = self.search([
            ('product_type', '=', 'opt'),
            ('opt_ids', '=', False)
        ])
        for product in opt_products:
            self.env['product.opt'].create({'product_tmpl_id': product.id})
        
        return True

