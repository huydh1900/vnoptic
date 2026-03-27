# -*- coding: utf-8 -*-
import base64
from io import BytesIO
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    """Extend product.category to add code field for product code generation"""
    _inherit = 'product.category'

    code = fields.Char('Mã danh mục', size=2, index=True,
                       help='Mã danh mục dùng cho phân loại & tạo mã sản phẩm (VD: TK=Tròng kính, GK=Gọng kính, PK=Phụ kiện)')
    group_ids = fields.One2many(
        'product.group',
        'category_id',
        string='Nhóm sản phẩm'
    )


class ProductTemplateExtension(models.Model):
    _inherit = 'product.template'

    len_type = fields.Selection([
        ('DT', 'Đơn tròng'),
        ('HT', 'Hai tròng'),
        ('DAT', 'Đa tròng'),
        ('PT', 'Phôi tròng'),
    ], string='Loại tròng')

    x_java_qr_url = fields.Char(string='QR URL (Java)', copy=False)
    barcode_image = fields.Binary(string='QR Code', compute='_compute_barcode_image', store=False)

    @api.depends('x_java_qr_url')
    def _compute_barcode_image(self):
        try:
            import qrcode
        except ImportError:
            for rec in self:
                rec.barcode_image = False
            return
        for rec in self:
            if rec.x_java_qr_url:
                img = qrcode.make(rec.x_java_qr_url)
                buf = BytesIO()
                img.save(buf, format='PNG')
                rec.barcode_image = base64.b64encode(buf.getvalue()).decode()
            else:
                rec.barcode_image = False

    def _get_category_by_code(self, code):
        return self.env['product.category'].search([('code', '=', code)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            name = vals.get('name')
            if name and self._name_is_lens_eye_prefix(name):
                tk_category = self._get_category_by_code('TK')
                if tk_category:
                    vals['categ_id'] = tk_category.id

            categ_id = vals.get('categ_id')
            if categ_id:
                inferred = self._infer_product_type_from_category(self.env['product.category'].browse(categ_id))
                if inferred in ('lens', 'opt', 'accessory'):
                    vals['product_type'] = inferred
        return super().create(vals_list)

    def write(self, vals):
        name = vals.get('name')
        if name and self._name_is_lens_eye_prefix(name):
            tk_category = self._get_category_by_code('TK')
            if tk_category:
                vals = dict(vals, categ_id=tk_category.id)

        if 'categ_id' in vals and vals.get('categ_id'):
            inferred = self._infer_product_type_from_category(self.env['product.category'].browse(vals['categ_id']))
            if inferred in ('lens', 'opt', 'accessory'):
                vals = dict(vals, product_type=inferred)
        return super().write(vals)

    def _infer_product_type_from_category(self, category):
        """Infer business product_type from product.category (code/name), walking up parents."""
        categ = category
        while categ:
            code = (getattr(categ, 'code', '') or '').strip()
            if code:
                code_upper = code.upper()
                # Hỗ trợ cả mã legacy (06/27/20) và mã mới theo file data (TK/GK/PK/TB/LK)
                if code_upper.startswith('06') or code_upper.startswith('TK'):
                    return 'lens'
                if code_upper.startswith('27') or code_upper.startswith('GK'):
                    return 'opt'
                if (code_upper.startswith('20')
                        or code_upper.startswith('PK')
                        or code_upper.startswith('TB')
                        or code_upper.startswith('LK')):
                    return 'accessory'
            categ = categ.parent_id

        # Fallback: infer from name keywords (when code is missing)
        name = (getattr(category, 'name', '') or '').strip().lower() if category else ''
        if any(k in name for k in ['tròng', 'trong', 'lens']):
            return 'lens'
        if any(k in name for k in ['gọng', 'gong', 'optical', 'opt']):
            return 'opt'
        if any(k in name for k in ['phụ kiện', 'phu kien', 'accessor']):
            return 'accessory'
        if any(k in name for k in ['all', 'tất cả', 'tat ca']):
            return False
        return False

    @api.onchange('categ_id')
    def _onchange_categ_id_reset_groups(self):
        """Switch UI group field by category; clear groups when category changes."""
        for rec in self:
            inferred = rec._infer_product_type_from_category(rec.categ_id)
            rec.lens_group_id = False
            rec.opt_group_id = False
            rec.acc_group_id = False
            rec.group_id = False
            rec.len_type = False
            rec.product_type = inferred

    @api.onchange('len_type')
    def _onchange_len_type_reset_group_id(self):
        for rec in self:
            if rec.product_type == 'lens':
                rec.group_id = False

    @api.constrains('default_code')
    def _constrains_default_code_unique(self):
        for rec in self:
            if not rec.default_code:
                continue
            if self.search_count([('id', '!=', rec.id), ('default_code', '=', rec.default_code)]):
                raise ValidationError("Mã viết tắt (default_code) phải là duy nhất.")

    # Keep product_type for now but make it computed or optional if needed
    # For now we just add the new logic alongside
    x_eng_name = fields.Char(
        'Tên tiếng Anh',
        help="Product name in English"
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

    # ==================== ACCESSORY FIELDS ====================
    design_id = fields.Many2one('product.design', string='Thiết kế')
    shape_id = fields.Many2one('product.shape', string='Hình dáng')
    material_id = fields.Many2one('product.material', string='Chất liệu')
    color_id = fields.Many2one('product.color', string='Màu sắc')
    acc_width = fields.Float('Chiều rộng')
    acc_length = fields.Float('Chiều dài')
    acc_height = fields.Float('Chiều cao')
    acc_head = fields.Float('Đầu')
    acc_body = fields.Float('Thân')

    lens_template_key = fields.Char(
        'Lens Template Key',
        index=True,
        copy=False,
        help='Key gom template lens (CID + Index + Material + Coating + Diameter + Brand)'
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
        'product.warranty', 'Bảo hành hãng',
        help="Product warranty (manufacturer)"
    )
    warranty_supplier_id = fields.Many2one(
        'product.warranty', 'Bảo hành công ty',
        help="Warranty provided by the company/supplier"
    )
    warranty_retail_id = fields.Many2one(
        'product.warranty', 'Bảo hành bán lẻ',
        help="Warranty for retail customers"
    )
    # Note: Supplier management uses standard Odoo field 'seller_ids' (One2many to product.supplierinfo)
    # This allows managing multiple suppliers with prices and conditions per supplier
    country_id = fields.Many2one(
        'res.country', 'Xuất xứ',
        help="Country of origin for the product"
    )

    # ==================== LENS/OPT RELATIONSHIPS ====================
    lens_ids = fields.One2many('product.lens', 'product_tmpl_id', 'Lens Details')
    # opt_ids giữ lại tạm để migrate dữ liệu cũ, KHÔNG dùng cho logic nghiệp vụ mới
    opt_ids = fields.One2many('product.opt', 'product_tmpl_id', 'Optical Details (Legacy)')

    # ==================== ADDITIONAL FIELDS FOR VIEW ====================
    group_id = fields.Many2one(
        'product.group',
        string='Nhóm sản phẩm',
        help='Nhóm sản phẩm (lọc theo cây danh mục).'
    )
    lens_group_id = fields.Many2one('product.group', string='Nhóm Tròng kính',
                                    domain=[('product_type', '=', 'lens')],
                                    help='Nhóm sản phẩm cho Tròng kính')
    opt_group_id = fields.Many2one('product.group', string='Nhóm Gọng kính',
                                   domain=[('product_type', '=', 'opt')],
                                   help='Nhóm sản phẩm cho Gọng kính')
    acc_group_id = fields.Many2one('product.group', string='Nhóm Phụ kiện',
                                   domain=[('product_type', '=', 'accessory')],
                                   help='Nhóm sản phẩm cho Phụ kiện')

    # NOTE: lens_group_id/opt_group_id/acc_group_id giữ lại để tương thích dữ liệu cũ,
    # UI hiện tại dùng group_id duy nhất và lọc theo danh mục.
    index_id = fields.Many2one('product.lens.index', string='Chiết suất',
                               help='Lens index for code generation (lens products only)')
    auto_generate_code = fields.Boolean('Tự động tạo mã', default=True,
                                        help='Automatically generate product code based on Group, Brand, and Index')
    status_product_id = fields.Many2one('product.status', 'Trạng thái')

    # ==================== LENS SPECS (Hướng B: field trực tiếp trên template) ====================
    # Thiết kế
    lens_sph_id = fields.Many2one('product.lens.power', string='SPH',
                                  help='Công suất cầu (Sphere)')
    lens_cyl_id = fields.Many2one('product.lens.power', string='CYL',
                                  help='Công suất trụ (Cylinder)')
    lens_add_id = fields.Many2one('product.lens.power', string='ADD',
                                  help='Addition (thấu kính đa tròng)')
    lens_base_curve = fields.Float('Base Curve', digits=(4, 2))
    lens_design1_id = fields.Many2one('product.design', string='Thiết kế 1')
    lens_design2_id = fields.Many2one('product.design', string='Thiết kế 2')

    # Chất liệu
    lens_material_id = fields.Many2one('product.lens.material', string='Vật liệu')
    lens_index_id = fields.Many2one('product.lens.index', string='Chiết suất')

    # Tích hợp
    lens_uv_id = fields.Many2one('product.uv', string='UV')
    lens_color_int = fields.Char('Độ đậm màu', size=50)
    lens_coating_ids = fields.Many2many(
        'product.coating',
        'product_tmpl_coating_rel', 'tmpl_id', 'coating_id',
        string='Coating'
    )
    # Màu sắc HMC / Photochromic / Tinted (từ clhmcdto / clphodto / clTintdto)
    lens_cl_hmc_id = fields.Many2one('product.cl', string='Màu HMC')
    lens_cl_pho_id = fields.Many2one('product.cl', string='Màu Photochromic')
    lens_cl_tint_id = fields.Many2one('product.cl', string='Màu Tinted')

    # ==================== LENS SPECS (Custom display-only fields) ====================
    x_sph = fields.Float('SPH', digits=(6, 2), help='Lens sphere power (display only)')
    x_cyl = fields.Float('CYL', digits=(6, 2), help='Lens cylinder power (display only)')
    x_add = fields.Float('ADD', digits=(6, 2), help='Lens add power (display only)')
    x_axis = fields.Integer('Axis', help='Lens axis (display only)')
    x_prism = fields.Char('Lăng kính', size=50, help='Lens prism (display only)')
    x_prism_base = fields.Char('Đáy lăng kính', size=50, help='Lens prism base (display only)')
    x_hmc = fields.Char('HMC (legacy)', help='Deprecated – dùng lens_cl_hmc_id')
    x_photochromic = fields.Char('Photochromic (legacy)', help='Deprecated – dùng lens_cl_pho_id')
    x_tinted = fields.Char('Tinted (legacy)', help='Deprecated – dùng lens_cl_tint_id')
    x_mir_coating = fields.Char('Màu tráng gương', help='Mirror coating (display only)')
    x_diameter = fields.Float('Đường kính (mm)', digits=(6, 1), help='Lens diameter (display only)')

    # ==================== OPT SPECS (Hướng B: field trực tiếp trên template) ====================
    # Thông tin cơ bản
    opt_season = fields.Char('Season', size=50)
    opt_model = fields.Char('Model', size=50)
    opt_serial = fields.Char('Serial', size=50)
    opt_oem_ncc = fields.Char('OEM NCC', size=50)
    opt_sku = fields.Char('SKU', size=50)
    opt_color = fields.Char('Màu sắc', size=50)
    opt_gender = fields.Selection([
        ('0', ''),
        ('1', 'Nam'), ('2', 'Nữ'), ('3', 'Unisex')
    ], string='Giới tính')

    # Kích thước
    opt_temple_width = fields.Integer('Chiều dài càng (mm)')
    opt_lens_width = fields.Integer('Chiều rộng tròng (mm)')
    opt_lens_span = fields.Integer('Khoảng cách tròng (mm)')
    opt_lens_height = fields.Integer('Chiều cao tròng (mm)')
    opt_bridge_width = fields.Integer('Cầu mũi (mm)')

    # Màu sắc
    # Màu sắc - Many2one (giữ tương thích legacy)
    opt_color_front_id = fields.Many2one('product.cl', string='Màu mặt trước')
    opt_color_temple_id = fields.Many2one('product.cl', string='Màu càng')
    opt_color_lens_id = fields.Many2one('product.cl', string='Màu mắt kính')
    # Màu sắc - Many2many (mới, hỗ trợ nhiều màu)
    opt_color_front_ids = fields.Many2many(
        'product.cl', 'product_tmpl_color_front_rel',
        'tmpl_id', 'cl_id', string='Màu mặt trước (M2M)'
    )
    opt_color_temple_ids = fields.Many2many(
        'product.cl', 'product_tmpl_color_temple_rel',
        'tmpl_id', 'cl_id', string='Màu càng kính (M2M)'
    )

    # Thiết kế
    opt_frame_id = fields.Many2one('product.frame', string='Loại gọng')
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

    # ==================== WARRANTY TEMPLATE (Hướng A – ERP chuẩn) ====================
    warranty_template_id = fields.Many2one(
        'product.warranty.template',
        string='Chính sách bảo hành',
        help='Chọn chính sách bảo hành áp dụng cho sản phẩm'
    )
    manufacturer_months = fields.Integer(
        string='Bảo hành NSX (tháng)',
        default=0,
        store=True,
        help='Số tháng bảo hành do nhà sản xuất cung cấp (tự động lấy từ warranty_id hoặc sync API)'
    )
    company_months = fields.Integer(
        string='Bảo hành công ty (tháng)',
        default=0,
        store=True,
        help='Số tháng bảo hành do công ty cam kết thêm (tự động lấy từ warranty_id hoặc sync API)'
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
    # Giá sỉ theo % = x_ws_price / list_price * 100 (computed, readonly)
    gia_si_theo_phan_tram = fields.Float(
        'Giá sỉ theo %',
        digits=(6, 2),
        compute='_compute_gia_si_theo_phan_tram',
        store=True,
        readonly=True,
        help='Tỷ lệ giá sỉ so với giá bán lẻ: x_ws_price / list_price × 100'
    )

    @api.depends('list_price', 'x_ws_price')
    def _compute_gia_si_theo_phan_tram(self):
        for record in self:
            if record.list_price:
                record.gia_si_theo_phan_tram = record.x_ws_price / record.list_price * 100.0
            else:
                record.gia_si_theo_phan_tram = 0.0

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

    @api.depends('lens_sph_id', 'lens_cyl_id', 'lens_add_id', 'lens_index_id')
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
    def migrate_sph_cyl_to_many2one(self):
        """Bước 3: Migrate x_sph/x_cyl/x_add (float legacy) → lens_sph_id/lens_cyl_id/lens_add_id (Many2one).
        Có thể gọi từ shell, cron, hoặc nút bấm wizard.

        Sau khi chạy xong, kiểm tra:
          SELECT count(*) FROM product_template
          WHERE (x_sph != 0 OR x_cyl != 0 OR x_add != 0)
            AND (lens_sph_id IS NULL AND lens_cyl_id IS NULL AND lens_add_id IS NULL);
        phải = 0.
        """
        import logging as _logging
        _log = _logging.getLogger(__name__)

        def _get_or_create_power(env, fval, power_type=None):
            if fval is None or fval == 0.0:
                return False
            formatted = f"{fval:+.2f}"
            rec = env['product.lens.power'].search([('value', '=', fval)], limit=1)
            if rec:
                return rec.id
            try:
                new_rec = env['product.lens.power'].create({'value': fval})
                return new_rec.id
            except Exception as e:
                _log.warning("⚠️ migrate: cannot create lens.power value=%s: %s", formatted, e)
                return False

        domain = [
            ('product_type', '=', 'lens'),
            '|', '|',
            ('x_sph', '!=', 0.0),
            ('x_cyl', '!=', 0.0),
            ('x_add', '!=', 0.0),
        ]
        templates = self.env['product.template'].search(domain)
        migrated = 0
        skipped = 0
        for tmpl in templates:
            write_vals = {}
            if tmpl.x_sph and not tmpl.lens_sph_id:
                pid = _get_or_create_power(self.env, tmpl.x_sph, 'sph')
                if pid:
                    write_vals['lens_sph_id'] = pid
            if tmpl.x_cyl and not tmpl.lens_cyl_id:
                pid = _get_or_create_power(self.env, tmpl.x_cyl, 'cyl')
                if pid:
                    write_vals['lens_cyl_id'] = pid
            if tmpl.x_add and not tmpl.lens_add_id:
                pid = _get_or_create_power(self.env, tmpl.x_add, 'add')
                if pid:
                    write_vals['lens_add_id'] = pid
            if write_vals:
                tmpl.write(write_vals)
                migrated += 1
            else:
                skipped += 1

        _log.warning(
            "✅ migrate_sph_cyl_to_many2one DONE: migrated=%s, skipped=%s, total=%s",
            migrated, skipped, len(templates)
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migration SPH/CYL/ADD xong',
                'message': f'Đã migrate {migrated} template. Skipped: {skipped}.',
                'type': 'success',
                'sticky': False,
            }
        }

    # ==================== PRODUCT CREATION LOGIC ====================
    @api.model_create_multi
    def create(self, vals_list):
        from ..utils import product_code_utils
        for vals in vals_list:
            if 'product_type' not in vals and vals.get('categ_id'):
                categ = self.env['product.category'].browse(vals['categ_id'])
                vals['product_type'] = self._infer_product_type_from_category(categ)

            # Auto-generate product code if enabled and not provided
            if vals.get('auto_generate_code', True) and not vals.get('default_code'):
                categ_id = vals.get('categ_id')
                brand_id = vals.get('brand_id')
                index_id = vals.get('index_id')
                if categ_id and brand_id:
                    try:
                        vals['default_code'] = product_code_utils.generate_product_code(
                            self.env, categ_id, brand_id, index_id
                        )
                    except Exception as e:
                        _logger.warning(f"Failed to auto-generate product code: {e}")

            product_type = vals.get('product_type', 'lens')
            if product_type != 'lens':
                vals.pop('lens_ids', None)
            if product_type != 'opt':
                vals.pop('opt_ids', None)

        products = super().create(vals_list)

        for product in products:
            if product.product_type == 'opt' and not product.opt_ids:
                self.env['product.opt'].create({'product_tmpl_id': product.id})

        return products

    def write(self, vals):
        if 'categ_id' in vals:
            # Clear groups when category changes, unless caller explicitly sets group fields.
            if not any(k in vals for k in ('lens_group_id', 'opt_group_id', 'acc_group_id', 'group_id')):
                vals.setdefault('lens_group_id', False)
                vals.setdefault('opt_group_id', False)
                vals.setdefault('acc_group_id', False)
                vals.setdefault('group_id', False)

            if 'product_type' not in vals and vals.get('categ_id'):
                categ = self.env['product.category'].browse(vals['categ_id'])
                vals['product_type'] = self._infer_product_type_from_category(categ)

        if 'product_type' in vals:
            new_type = vals['product_type']
            if new_type != 'lens':
                self.mapped('lens_ids').unlink()
                vals.pop('lens_ids', None)
            if new_type != 'opt':
                self.mapped('opt_ids').unlink()
                vals.pop('opt_ids', None)
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
