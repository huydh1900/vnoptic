# -*- coding: utf-8 -*-
import base64
import logging
from io import BytesIO
from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    """Extend product.category to add code field for product code generation"""
    _inherit = 'product.category'

    code = fields.Char('Mã danh mục', size=2, index=True,
                       help='Mã danh mục dùng cho phân loại & tạo mã sản phẩm (VD: TK=Tròng kính, GK=Gọng kính, PK=Phụ kiện)')



class ProductTemplateExtension(models.Model):
    _inherit = 'product.template'

    len_type = fields.Selection([
        ('SV', 'SV - Đơn tròng (Single Vision)'),
        ('BF', 'BF - Hai tròng (Bifocal)'),
        ('TF', 'TF - Ba tròng (Trifocal)'),
        ('PRO', 'PRO - Đa tròng (Progressive)'),
        ('PT', 'PT - Phôi tròng'),
        # Legacy values (giữ để không break dữ liệu cũ)
        ('DT', 'DT - Đơn tròng (legacy)'),
        ('HT', 'HT - Hai tròng (legacy)'),
        ('DAT', 'DAT - Đa tròng (legacy)'),
    ], string='Loại tròng')

    x_java_qr_url = fields.Char(string='QR URL (Java)', copy=False)
    qr_code = fields.Binary(string='QR Code', compute='_compute_qr_code', store=False)

    @api.depends('x_java_qr_url')
    def _compute_qr_code(self):
        try:
            import qrcode
        except ImportError:
            for rec in self:
                rec.qr_code = False
            return
        for rec in self:
            if rec.x_java_qr_url:
                img = qrcode.make(rec.x_java_qr_url)
                buf = BytesIO()
                img.save(buf, format='PNG')
                rec.qr_code = base64.b64encode(buf.getvalue()).decode()
            else:
                rec.qr_code = False

    def _get_category_by_code(self, code):
        return self.env['product.category'].search([('code', '=', code)], limit=1)

    @api.onchange('categ_id', 'classification_id')
    def _onchange_categ_id_reset_groups(self):
        """Clear len_type khi danh mục/phân loại đổi."""
        for rec in self:
            rec.len_type = False

    @api.constrains('barcode')
    def _constrains_barcode_unique(self):
        for rec in self:
            if not rec.barcode:
                continue
            if self.search_count([('id', '!=', rec.id), ('barcode', '=', rec.barcode)]):
                raise ValidationError("Barcode phải là duy nhất.")

    x_eng_name = fields.Char(
        'Tên tiếng Anh',
        help="Product name in English"
    )

    x_short_name = fields.Char(
        'Tên rút gọn',
        help='Tên sản phẩm rút gọn (hiển thị tem, tree view, in mã)'
    )

    x_base_price = fields.Float(
        'Giá bán cơ sở có thuế',
        digits='Product Price',
        help='Giá bán cơ sở (đã bao thuế) — dùng làm cơ sở so sánh markup. Khác list_price là giá bán lẻ.'
    )

    x_invoice_name = fields.Char(
        'Tên viết hóa đơn',
        help="Tên sản phẩm dùng để in trên hóa đơn"
    )

    x_uses = fields.Text(
        'Công dụng',
        help="Product usage instructions"
    )

    x_guide = fields.Text(
        'Hướng dẫn sử dụng',
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
        'Giá sỉ tối thiểu',
        digits='Product Price',
        help="Minimum wholesale price"
    )

    x_ws_price_max = fields.Float(
        'Giá sỉ tối đa',
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
    acc_width = fields.Float('Chiều rộng', digits=(6, 2))
    acc_length = fields.Float('Chiều dài', digits=(6, 2))
    acc_height = fields.Float('Chiều cao', digits=(6, 2))
    acc_head = fields.Float('Đầu', digits=(6, 2))
    acc_body = fields.Float('Thân', digits=(6, 2))

    lens_template_key = fields.Char(
        'Lens Template Key',
        index=True,
        copy=False,
        help='Key gom template lens (CID + Index + Material + Coating + Diameter + Brand)'
    )

    # ==================== PRODUCT TYPE (for sync categorization) ====================
    categ_code = fields.Char(
        string='Mã danh mục',
        compute='_compute_categ_code',
        store=True,
        help="Mã danh mục gốc (walk up parent tree): TK=Tròng kính, GK=Gọng kính, PK/TB/LK=Phụ kiện..."
    )

    @api.depends('categ_id', 'categ_id.code', 'categ_id.parent_id', 'categ_id.parent_id.code')
    def _compute_categ_code(self):
        for rec in self:
            categ = rec.categ_id
            code = ''
            while categ:
                code = (getattr(categ, 'code', '') or '').strip().upper()
                if code:
                    break
                categ = categ.parent_id
            rec.categ_code = code

    # ==================== CLASSIFICATION (Nhóm sản phẩm mới) ====================
    classification_id = fields.Many2one(
        'product.classification',
        string='Nhóm sản phẩm',
        index=True,
        help='Phân loại nhóm sản phẩm (Gọng kính / Tròng kính / Phụ kiện / Khác) qua product.classification.category_type'
    )
    classification_type = fields.Selection(
        related='classification_id.category_type',
        string='Loại sản phẩm',
        store=True,
        index=True,
        help='Phân biệt frame / lens / accessory / other dựa trên classification_id.category_type'
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
    index_id = fields.Many2one('product.lens.index', string='Chiết suất',
                               help='Lens index for code generation (lens products only)')
    product_status = fields.Selection([
        ('new', 'Mới'),
        ('current', 'Hiện hành'),
    ], string='Trạng thái')

    label_print_type = fields.Selection([
        ('0', 'Không in tem'),
        ('1', 'In tem mắt'),
        ('2', 'In tem gọng'),
        ('3', 'Không thể dán tem'),
    ], string='Kiểu in nhãn', default='0')

    # ==================== LENS SPECS (Hướng B: field trực tiếp trên template) ====================
    # Thiết kế / Vật liệu / Hình học
    lens_category = fields.Char('Hạng mục tròng kính', size=100)
    lens_base_curve = fields.Float('Độ cong kính', digits=(6, 2))
    lens_design_ids = fields.Many2many(
        'product.design',
        'product_tmpl_lens_design_rel', 'tmpl_id', 'design_id',
        string='Thiết kế'
    )

    # Chất liệu
    lens_material_ids = fields.Many2many(
        'product.lens.material',
        'product_tmpl_lens_material_rel', 'tmpl_id', 'material_id',
        string='Chất liệu'
    )
    lens_index_id = fields.Many2one('product.lens.index', string='Chiết suất')
    lens_film_ids = fields.Many2many(
        'product.lens.film',
        'product_tmpl_lens_film_rel', 'tmpl_id', 'film_id',
        string='Lớp film chức năng'
    )

    # Tích hợp
    lens_uv_id = fields.Many2one('product.uv', string='Chống UV')
    lens_light_transmission = fields.Float('Tỷ lệ ánh sáng truyền qua (%)', digits=(6, 2))
    lens_color_int = fields.Char('Độ đậm màu', size=50)
    lens_polarized = fields.Boolean('Mạ polarized')
    lens_coating_ids = fields.Many2many(
        'product.coating',
        'product_tmpl_coating_rel', 'tmpl_id', 'coating_id',
        string='Lớp phủ'
    )
    lens_mirror_coating = fields.Char('Ánh mạ', size=100)
    lens_color_coating = fields.Char('Mạ màu', size=100)
    lens_mirror_color = fields.Char('Màu phủ gương', size=100)
    lens_abbe = fields.Float('Chỉ số tán sắc (Abbe)', digits=(6, 2))
    lens_corridor = fields.Float('Corridor (mm)', digits=(6, 2))
    lens_hard_soft = fields.Selection([
        ('hard', 'Cứng'),
        ('soft', 'Mềm'),
    ], string='Cứng/Mềm (áp tròng)')
    lens_features = fields.Char('Đặc tính', size=200)
    lens_eye_side = fields.Selection([
        ('left', 'Trái'),
        ('right', 'Phải'),
        ('both', 'Cả hai'),
    ], string='Trái/Phải')
    # Màu sắc HMC / Photochromic / Tinted (từ clhmcdto / clphodto / clTIntdto)
    lens_cl_hmc_id = fields.Many2one('product.cl', string='HMC')
    lens_cl_pho_id = fields.Many2one('product.cl', string='Đổi màu')
    lens_cl_tint_id = fields.Many2one('product.cl', string='Tinted')

    # ==================== LENS SPECS (Selection cho SPH/CYL) ====================
    # SPH: từ -10.50 đến -20.00, bước 0.5
    _SPH_VALUES = [f"-{v / 100:.2f}" for v in range(1050, 2050, 50)]
    # CYL: từ -2.25 đến -4.00, bước 0.25
    _CYL_VALUES = [f"-{v / 100:.2f}" for v in range(225, 425, 25)]

    x_sph = fields.Selection(
        selection=[(v, v) for v in _SPH_VALUES],
        string='Độ cầu (SPH)',
        index=True,
        help='Công suất cầu (Sphere): -10.50 → -20.00, bước 0.50'
    )
    x_cyl = fields.Selection(
        selection=[(v, v) for v in _CYL_VALUES],
        string='Độ trụ (CYL)',
        index=True,
        help='Công suất trụ (Cylinder): -2.25 → -4.00, bước 0.25'
    )
    x_add = fields.Float('Độ cộng thêm (ADD)', digits=(6, 2), help='Lens add power (display only)')
    x_axis = fields.Integer('Trục (AXIS)', help='Lens axis (0-180)')
    x_prism = fields.Float('Lăng kính (Prism)', digits=(6, 2), help='Lens prism (display only)')
    x_prism_base = fields.Char('Đáy lăng kính', size=50, help='Lens prism base (display only)')

    @api.constrains('x_axis')
    def _check_x_axis_range(self):
        for rec in self:
            if rec.x_axis and not (0 <= rec.x_axis <= 180):
                raise ValidationError('Trục (AXIS) phải nằm trong khoảng 0–180.')
    x_mir_coating = fields.Char('Màu tráng gương', help='Mirror coating (display only)')
    x_diameter = fields.Float('Đường kính (mm)', digits=(6, 2), help='Lens diameter (display only)')

    # ==================== OPT SPECS (Hướng B: field trực tiếp trên template) ====================
    # Thông tin cơ bản
    opt_season = fields.Char('Season', size=50)
    opt_model = fields.Char('Model', size=50)
    opt_serial = fields.Char('Serial', size=50)
    opt_sku = fields.Char('SKU', size=50)
    opt_color = fields.Char('Mã màu', size=50)
    opt_gender = fields.Selection([
        ('M', 'Nam (M)'),
        ('F', 'Nữ (F)'),
        ('U', 'Unisex (U)'),
        ('K-M', 'Trẻ em - Nam (K-M)'),
        ('K-F', 'Trẻ em - Nữ (K-F)'),
        ('K-U', 'Trẻ em - Unisex (K-U)'),
        # Legacy numeric values
        ('1', 'Nam (legacy)'),
        ('2', 'Nữ (legacy)'),
        ('3', 'Unisex (legacy)'),
    ], string='Giới tính')

    # Kích thước
    opt_temple_width = fields.Integer('Chiều dài càng (mm)')
    opt_lens_width = fields.Integer('Chiều rộng tròng (mm)')
    opt_lens_span = fields.Integer('Khoảng cách tròng (mm)')
    opt_lens_height = fields.Integer('Chiều cao tròng (mm)')
    opt_bridge_width = fields.Integer('Cầu mũi (mm)')

    # Khối lượng & đá quý
    opt_weight = fields.Float('Trọng lượng (g)', digits=(6, 2))
    opt_gem_count = fields.Integer('Số lượng đá quý')
    opt_gem_carat = fields.Float('Carat đá quý', digits=(6, 2))

    # Màu sắc (Char free text)
    opt_color_lens = fields.Char('Màu mắt kính', size=100)
    opt_color_front = fields.Char('Màu mặt trước', size=100)
    opt_color_temple = fields.Char('Màu càng kính', size=100)

    # Thiết kế
    opt_frame_style = fields.Char('Kiểu gọng', size=100)
    opt_frame_type_id = fields.Many2one('product.frame.type', string='Loại gọng')
    opt_frame_structure_id = fields.Many2one('product.frame.structure', string='Cấu trúc vành')
    opt_shape_id = fields.Many2one('product.shape', string='Dáng mắt')
    opt_ve_id = fields.Many2one('product.ve', string='Loại ve')
    opt_temple_tip_id = fields.Many2one('product.temple.tip', string='Loại chuôi càng')
    opt_temple_style = fields.Char('Càng kính (mô tả)', size=100)
    opt_polarized = fields.Boolean('Mạ mắt polarized')

    # Chất liệu
    opt_material_ve_id = fields.Many2one('product.material', string='Ve kính')
    opt_material_temple_tip_ids = fields.Many2many(
        'product.material', 'product_tmpl_material_temple_tip_rel',
        'tmpl_id', 'material_id', string='Chuôi càng'
    )
    opt_material_lens_id = fields.Many2one('product.material', string='Mắt kính')
    opt_materials_front_ids = fields.Many2many(
        'product.material', 'product_tmpl_material_front_rel',
        'tmpl_id', 'material_id', string='Mặt trước'
    )
    opt_materials_temple_ids = fields.Many2many(
        'product.material', 'product_tmpl_material_temple_rel',
        'tmpl_id', 'material_id', string='Càng'
    )
    opt_coating_ids = fields.Many2many(
        'product.coating', 'product_tmpl_opt_coating_rel',
        'tmpl_id', 'coating_id', string='Lớp mạ'
    )

    # ==================== WARRANTY TEMPLATE (Hướng A – ERP chuẩn) ====================
    manufacturer_months = fields.Integer(
        string='Bảo hành hãng (tháng)',
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
    cao_mat = fields.Float(
        'Cao mắt (mm)',
        digits=(6, 2),
        help='Chiều cao mắt kính'
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

    @api.depends('x_sph', 'x_cyl', 'lens_index_id')
    def _compute_lens_info(self):
        for record in self:
            record.lens_sph = record.x_sph or ''
            record.lens_cyl = record.x_cyl or ''
            record.lens_index_name = record.lens_index_id.name if record.lens_index_id else ''

    @api.depends('opt_frame_type_id', 'opt_shape_id')
    def _compute_opt_info(self):
        for record in self:
            record.opt_frame_type = record.opt_frame_type_id.name if record.opt_frame_type_id else ''
            record.opt_shape = record.opt_shape_id.name if record.opt_shape_id else ''

    # ==================== COMPUTED FIELD FOR PRIMARY SUPPLIER ====================
    primary_supplier_id = fields.Many2one('res.partner', string='Nhà cung cấp chính',
                                          compute='_compute_primary_supplier', store=True, readonly=True,
                                          help='Nhà cung cấp chính (lấy từ seller_ids đầu tiên)')

    x_supplier_name = fields.Char(
        string='Tên nguồn cung cấp',
        related='primary_supplier_id.name',
        store=True, readonly=True,
        help='Tên đầy đủ của NCC chính (đồng bộ từ seller_ids đầu tiên).'
    )
    x_supplier_ref = fields.Char(
        string='Mã NCC',
        related='primary_supplier_id.ref',
        store=True, readonly=True,
        help='Mã (ref) của NCC chính.'
    )

    @api.depends('seller_ids', 'seller_ids.partner_id')
    def _compute_primary_supplier(self):
        for record in self:
            if record.seller_ids:
                record.primary_supplier_id = record.seller_ids[0].partner_id
            else:
                record.primary_supplier_id = False

