# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductCategory(models.Model):
    """Extend product.category to add code field for product code generation"""
    _inherit = 'product.category'
    
    code = fields.Char('Mã danh mục', size=2, index=True,
                       help='Mã 2 số dùng cho tạo mã sản phẩm (VD: 06=Tròng kính, 27=Gọng kính, 20=Phụ kiện)')


class ProductTemplateExtension(models.Model):
    _inherit = 'product.template'

    # Computed fields to replace product_type for UI logic
    is_lens = fields.Boolean(compute='_compute_product_kind', store=True)
    is_opt = fields.Boolean(compute='_compute_product_kind', store=True)

    @api.depends('categ_id', 'categ_id.code')
    def _compute_product_kind(self):
        for record in self:
            code = record.categ_id.code
            # 06 = Lens, 27 = Opt (Frame)
            record.is_lens = (code == '06')
            record.is_opt = (code == '27')

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
    opt_ids = fields.One2many('product.opt', 'product_tmpl_id', 'Optical Details')

    # ==================== ADDITIONAL FIELDS FOR VIEW ====================
    group_id = fields.Many2one('product.group', string='Nhóm sản phẩm (theo loại)',
                                help='Nhóm sản phẩm - tự động lọc theo phân loại nghiệp vụ')
    index_id = fields.Many2one('product.lens.index', string='Chiết suất', 
                                help='Lens index for code generation (lens products only)')
    auto_generate_code = fields.Boolean('Tự động tạo mã', default=True,
                                         help='Automatically generate product code based on Group, Brand, and Index')
    status_product_id = fields.Many2one('product.status', 'Trạng thái')

    # ==================== COMPUTED FIELDS FOR TREE VIEW ====================
    # Lens fields
    lens_sph = fields.Char('SPH', compute='_compute_lens_info', store=False, readonly=True)
    lens_cyl = fields.Char('CYL', compute='_compute_lens_info', store=False, readonly=True)
    lens_index_name = fields.Char('Index', compute='_compute_lens_info', store=False, readonly=True)
    lens_add = fields.Char('Add', compute='_compute_lens_info', store=False, readonly=True)
    
    # Opt fields
    opt_model = fields.Char('Model', compute='_compute_opt_info', store=False, readonly=True)
    opt_color = fields.Char('Color', compute='_compute_opt_info', store=False, readonly=True)
    opt_frame_type = fields.Char('Frame Type', compute='_compute_opt_info', store=False, readonly=True)
    opt_shape = fields.Char('Shape', compute='_compute_opt_info', store=False, readonly=True)
    
    @api.depends('lens_ids', 'lens_ids.sph', 'lens_ids.cyl', 'lens_ids.index_id', 'lens_ids.len_add', 'product_type')
    def _compute_lens_info(self):
        for record in self:
            if record.product_type == 'lens' and record.lens_ids:
                lens = record.lens_ids[0]
                record.lens_sph = lens.sph or ''
                record.lens_cyl = lens.cyl or ''
                record.lens_index_name = lens.index_id.name if lens.index_id else ''
                record.lens_add = lens.len_add or ''
            else:
                record.lens_sph = ''
                record.lens_cyl = ''
                record.lens_index_name = ''
                record.lens_add = ''
    
    @api.depends('opt_ids', 'opt_ids.model', 'opt_ids.color', 'opt_ids.frame_type_id', 'opt_ids.shape_id', 'product_type')
    def _compute_opt_info(self):
        for record in self:
            if record.product_type == 'opt' and record.opt_ids:
                opt = record.opt_ids[0]
                record.opt_model = opt.model or ''
                record.opt_color = opt.color or ''
                record.opt_frame_type = opt.frame_type_id.name if opt.frame_type_id else ''
                record.opt_shape = opt.shape_id.name if opt.shape_id else ''
            else:
                record.opt_model = ''
                record.opt_color = ''
                record.opt_frame_type = ''
                record.opt_shape = ''

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
        
        # Auto-create lens/opt record if needed
        if product_type == 'lens' and not product.lens_ids:
            self.env['product.lens'].create({'product_tmpl_id': product.id})
        elif product_type == 'opt' and not product.opt_ids:
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
        """Create missing lens/opt records for products that have product_type but no details"""
        created_lens = 0
        created_opt = 0
        
        for product in self:
            if product.product_type == 'lens' and not product.lens_ids:
                self.env['product.lens'].create({'product_tmpl_id': product.id})
                created_lens += 1
            elif product.product_type == 'opt' and not product.opt_ids:
                self.env['product.opt'].create({'product_tmpl_id': product.id})
                created_opt += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Đã tạo records',
                'message': f'Tạo {created_lens} lens, {created_opt} opt records',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def cron_create_all_missing_details(self):
        """Cron job to create missing lens/opt records for ALL products"""
        # Create lens records for lens products without details
        lens_products = self.search([
            ('product_type', '=', 'lens'),
            ('lens_ids', '=', False)
        ])
        for product in lens_products:
            self.env['product.lens'].create({'product_tmpl_id': product.id})
        
        # Create opt records for opt products without details
        opt_products = self.search([
            ('product_type', '=', 'opt'),
            ('opt_ids', '=', False)
        ])
        for product in opt_products:
            self.env['product.opt'].create({'product_tmpl_id': product.id})
        
        return True

