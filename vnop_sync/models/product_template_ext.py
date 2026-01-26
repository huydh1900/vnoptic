# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductTemplateExtension(models.Model):
    _inherit = 'product.template'

    eng_name = fields.Char(
        'Tên tiếng Anh',
        help="Product name in English"
    )

    trade_name = fields.Char(
        'Tên thương mại',
        help="Commercial trade name"
    )

    note_long = fields.Text(
        'Mô tả chi tiết',
        help="Detailed product description"
    )

    uses = fields.Text(
        'Công dụng',
        help="Product usage instructions"
    )

    guide = fields.Text(
        'Hướng dẫn sử dụng',
        help="Step-by-step usage guide"
    )

    warning = fields.Text(
        'Cảnh báo',
        help="Safety warnings and precautions"
    )

    preserve = fields.Text(
        'Bảo quản',
        help="Storage and preservation guidelines"
    )

    # ==================== SUPPLIER & STATUS FIELDS ====================

    cid_ncc = fields.Char(
        'Mã NCC',
        help="Supplier product code"
    )

    accessory_total = fields.Integer(
        'Tổng phụ kiện',
        default=0,
        help="Number of accessories included"
    )

    status_name = fields.Char(
        'Trạng thái sản phẩm',
        help="Current product status from API"
    )


    tax_percent = fields.Float(
        'Thuế (%)',
        digits=(5, 2),
        help="Tax rate percentage"
    )

    # Note: Retail price uses standard Odoo field 'list_price'

    ws_price = fields.Float(
        'Giá sỉ',
        digits='Product Price',
        help="Wholesale price"
    )

    ct_price = fields.Float(
        'Giá vốn',
        digits='Product Price',
        help="Cost price"
    )

    or_price = fields.Float(
        'Giá gốc',
        digits='Product Price',
        help="Original price from supplier"
    )

    ws_price_min = fields.Float(
        'Giá sỉ Min',
        digits='Product Price',
        help="Minimum wholesale price"
    )

    ws_price_max = fields.Float(
        'Giá sỉ Max',
        digits='Product Price',
        help="Maximum wholesale price"
    )


    currency_zone_code = fields.Char(
        'Mã vùng tiền tệ',
        help="Currency zone code from API"
    )

    currency_zone_value = fields.Float(
        'Tỷ giá',
        digits=(12, 2),
        help="Currency zone exchange rate"
    )


    group_type_name = fields.Char(
        'Loại nhóm sản phẩm',
        help="Product group type classification"
    )

    # ==================== PRODUCT TYPE (for sync categorization) ====================
    product_type = fields.Selection([
        ('lens', 'Tròng kính'),
        ('opt', 'Gọng kính'),
        ('accessory', 'Phụ kiện')
    ], string='Loại sản phẩm', default='lens',
       help="Product type for categorization (Lens/Optical/Accessory)"
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
    supplier_id = fields.Many2one(
        'res.partner', 'Nhà cung cấp',
        domain=[('supplier_rank', '>', 0)],
        help="Product supplier"
    )
    country_id = fields.Many2one(
        'product.country', 'Xuất xứ',
        help="Country of origin for the product"
    )

    # ==================== LENS/OPT RELATIONSHIPS ====================
    lens_ids = fields.One2many('product.lens', 'product_tmpl_id', 'Lens Details')
    opt_ids = fields.One2many('product.opt', 'product_tmpl_id', 'Optical Details')

    # ==================== ADDITIONAL FIELDS FOR VIEW ====================
    group_id = fields.Many2one('product.group', string='Nhóm SP')
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

    # ==================== PRODUCT CREATION LOGIC ====================
    @api.model
    def create(self, vals):
        # Auto-generate product code if enabled and not provided
        if vals.get('auto_generate_code', True) and not vals.get('default_code'):
            group_id = vals.get('group_id')
            brand_id = vals.get('brand_id')
            index_id = vals.get('index_id')  # For lens products
            
            if group_id and brand_id:
                from ..utils import product_code_utils
                try:
                    code = product_code_utils.generate_product_code(
                        self.env, group_id, brand_id, index_id
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

