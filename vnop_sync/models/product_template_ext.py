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
    group_ids = fields.One2many(
        'product.group',
        'category_id',
        string='Nhóm sản phẩm'
    )




class ProductTemplateExtension(models.Model):
    _inherit = 'product.template'

    def _vnop_normalize_import_name(self, value):
        import unicodedata, re
        text = (value or '').strip().lower()
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r'[^a-z0-9]+', '', text)
        return text

    def _check_duplicate_name(self, vals_list_or_vals, existing_ids=None):
        # Support both create (list) and write (dict)
        if isinstance(vals_list_or_vals, dict):
            vals_list = [vals_list_or_vals]
        else:
            vals_list = vals_list_or_vals
        existing_ids = existing_ids or []
        names = set()
        for vals in vals_list:
            name = vals.get('name')
            if not name:
                continue
            name_key = self._vnop_normalize_import_name(name)
            if name_key in names:
                raise ValidationError('Trùng tên sản phẩm trong cùng thao tác (%s).' % name)
            names.add(name_key)
            # Check DB (match spacing differences by interleaving %)
            name_pattern = '%'.join(list(name_key))
            domain = [('id', 'not in', existing_ids), ('active', 'in', [True, False])]
            domain.append(('name', 'ilike', name_pattern))
            for rec in self.env['product.template'].search(domain, limit=20):
                if self._vnop_normalize_import_name(rec.name) == name_key:
                    raise ValidationError('Tên sản phẩm đã tồn tại trong hệ thống (%s).' % name)

    _BASE36_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    _DEFAULT_CODE_SUFFIX_LEN = 5
    _DEFAULT_CODE_SUFFIX_MAX = (36 ** _DEFAULT_CODE_SUFFIX_LEN) - 1

    len_type = fields.Selection([
        ('DT', 'Đơn tròng'),
        ('HT', 'Hai tròng'),
        ('DAT', 'Đa tròng'),
        ('PT', 'Phôi tròng'),
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

    def _get_root_categ_code(self):
        """Walk up category tree and return the first code found."""
        categ = self.categ_id
        while categ:
            code = (getattr(categ, 'code', '') or '').strip().upper()
            if code:
                return code
            categ = categ.parent_id
        return ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            name = vals.get('name')
            if name and self._name_is_lens_eye_prefix(name):
                tk_category = self._get_category_by_code('TK')
                if tk_category:
                    vals['categ_id'] = tk_category.id
        return super().create(vals_list)

    def write(self, vals):
        name = vals.get('name')
        if name and self._name_is_lens_eye_prefix(name):
            tk_category = self._get_category_by_code('TK')
            if tk_category:
                vals = dict(vals, categ_id=tk_category.id)
        return super().write(vals)

    @api.onchange('categ_id')
    def _onchange_categ_id_reset_groups(self):
        """Clear groups when category changes."""
        for rec in self:
            rec.lens_group_id = False
            rec.opt_group_id = False
            rec.acc_group_id = False
            rec.group_id = False
            rec.len_type = False

    @api.onchange('len_type')
    def _onchange_len_type_reset_group_id(self):
        for rec in self:
            if rec._get_root_categ_code() == 'TK':
                rec.group_id = False

    @api.constrains('default_code')
    def _constrains_default_code_unique(self):
        for rec in self:
            if not rec.default_code:
                continue
            if self.search_count([('id', '!=', rec.id), ('default_code', '=', rec.default_code)]):
                raise ValidationError("Mã viết tắt (default_code) phải là duy nhất.")

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
        string='Phân nhóm phụ',
        help='Nhóm sản phẩm (lọc theo cây danh mục).'
    )
    lens_group_id = fields.Many2one('product.group', string='Nhóm Tròng kính',
                                    domain=[('category_id.code', '=', 'TK')],
                                    help='Nhóm sản phẩm cho Tròng kính')
    opt_group_id = fields.Many2one('product.group', string='Nhóm Gọng kính',
                                   domain=[('category_id.code', '=', 'GK')],
                                   help='Nhóm sản phẩm cho Gọng kính')
    acc_group_id = fields.Many2one('product.group', string='Nhóm Phụ kiện',
                                   domain=[('category_id.code', 'in', ('PK', 'TB', 'LK'))],
                                   help='Nhóm sản phẩm cho Phụ kiện')

    # NOTE: lens_group_id/opt_group_id/acc_group_id giữ lại để tương thích dữ liệu cũ,
    # UI hiện tại dùng group_id duy nhất và lọc theo danh mục.
    index_id = fields.Many2one('product.lens.index', string='Chiết suất',
                               help='Lens index for code generation (lens products only)')
    auto_generate_code = fields.Boolean('Tự động tạo mã', default=True,
                                        help='Automatically generate product code based on Group, Brand, and Index')
    product_status = fields.Selection([
        ('new', 'Mới'),
        ('current', 'Hiện hành'),
    ], string='Trạng thái')

    # ==================== LENS SPECS (Hướng B: field trực tiếp trên template) ====================
    # Thiết kế
    lens_sph_id = fields.Many2one('product.lens.power', string='SPH',
                                  help='Công suất cầu (Sphere)')
    lens_cyl_id = fields.Many2one('product.lens.power', string='CYL',
                                  help='Công suất trụ (Cylinder)')
    lens_add_id = fields.Many2one('product.lens.add', string='ADD',
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
    # Màu sắc HMC / Photochromic / Tinted (từ clhmcdto / clphodto / clTIntdto)
    lens_cl_hmc_id = fields.Many2one('product.cl', string='HMC')
    lens_cl_pho_id = fields.Many2one('product.cl', string='Photochromic')
    lens_cl_tint_id = fields.Many2one('product.cl', string='Tinted')

    # ==================== LENS SPECS (Custom display-only fields) ====================
    x_sph = fields.Float('SPH', digits=(6, 2), help='Lens sphere power (display only)')
    x_cyl = fields.Float('CYL', digits=(6, 2), help='Lens cylinder power (display only)')
    x_add = fields.Float('ADD', digits=(6, 2), help='Lens add power (display only)')
    x_axis = fields.Integer('Axis', help='Lens axis (display only)')
    x_prism = fields.Char('Lăng kính', size=50, help='Lens prism (display only)')
    x_prism_base = fields.Char('Đáy lăng kính', size=50, help='Lens prism base (display only)')
    x_mir_coating = fields.Char('Màu tráng gương', help='Mirror coating (display only)')
    x_diameter = fields.Float('Đường kính (mm)', digits=(6, 1), help='Lens diameter (display only)')

    # ==================== OPT SPECS (Hướng B: field trực tiếp trên template) ====================
    # Thông tin cơ bản
    opt_season = fields.Char('Season', size=50)
    opt_model = fields.Char('Model', size=50)
    opt_serial = fields.Char('Serial', size=50)
    opt_sku = fields.Char('SKU', size=50)
    opt_color = fields.Char('Mã màu', size=50)
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
    opt_color_lens_id = fields.Many2one('product.cl', string='Màu mắt kính (trường mắt)')
    # Màu sắc - Many2many (mới, hỗ trợ nhiều màu)
    opt_color_front_ids = fields.Many2many(
        'product.cl', 'product_tmpl_color_front_rel',
        'tmpl_id', 'cl_id', string='Màu mặt trước'
    )
    opt_color_temple_ids = fields.Many2many(
        'product.cl', 'product_tmpl_color_temple_rel',
        'tmpl_id', 'cl_id', string='Màu càng kính'
    )

    # Thiết kế
    opt_frame_id = fields.Many2one('product.frame', string='Loại gọng')
    opt_frame_type_id = fields.Many2one('product.frame.type', string='Kiểu loại')
    opt_shape_id = fields.Many2one('product.shape', string='Kiểu dáng')
    opt_ve_id = fields.Many2one('product.ve', string='Ve')
    opt_temple_id = fields.Many2one('product.temple', string='Càng kính')

    # Chất liệu
    opt_material_ve_id = fields.Many2one('product.material', string='Ve kính')
    opt_material_temple_tip_id = fields.Many2one('product.material', string='Chuôi càng')
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
                                          compute='_compute_primary_supplier', store=True, readonly=True,
                                          help='Nhà cung cấp chính (lấy từ seller_ids đầu tiên)')

    @api.depends('seller_ids', 'seller_ids.partner_id')
    def _compute_primary_supplier(self):
        for record in self:
            if record.seller_ids:
                record.primary_supplier_id = record.seller_ids[0].partner_id
            else:
                record.primary_supplier_id = False

    # ==================== PRODUCT CREATION LOGIC ====================
    @api.model_create_multi
    def create(self, vals_list):
        self._check_duplicate_name(vals_list)
        sequence_cache = {}
        for vals in vals_list:
            # Auto-generate product code if enabled and not provided
            if vals.get('auto_generate_code', True) and not vals.get('default_code'):
                categ_id = vals.get('categ_id')
                brand_id = vals.get('brand_id')
                group_id = vals.get('group_id')
                lens_index_id = vals.get('lens_index_id') or vals.get('index_id')
                if group_id and brand_id:
                    try:
                        vals['default_code'] = self._auto_generate_product_code(
                            categ_id,
                            brand_id,
                            lens_index_id,
                            group_id=group_id,
                            sequence_cache=sequence_cache,
                        )
                    except Exception as e:
                        _logger.warning(f"Failed to auto-generate product code: {e}")

        return super().create(vals_list)

    def _product_code_base36_to_int(self, value):
        text = (value or '').strip().upper()
        if not text:
            raise ValidationError('Suffix mã sản phẩm rỗng.')
        result = 0
        for ch in text:
            pos = self._BASE36_ALPHABET.find(ch)
            if pos < 0:
                raise ValidationError(f'Suffix mã sản phẩm không hợp lệ: {value}')
            result = result * 36 + pos
        return result

    def _product_code_int_to_base36(self, value, width):
        if value < 0:
            raise ValidationError('Suffix mã sản phẩm không được âm.')
        if value > self._DEFAULT_CODE_SUFFIX_MAX:
            raise ValidationError('Đã vượt giới hạn suffix 5 ký tự base36 cho mã sản phẩm.')
        if value == 0:
            text = '0'
        else:
            chars = []
            number = value
            while number:
                number, rem = divmod(number, 36)
                chars.append(self._BASE36_ALPHABET[rem])
            text = ''.join(reversed(chars))
        return text.rjust(width, '0')

    def _get_root_category_code_from_id(self, categ_id):
        if not categ_id:
            return ''
        categ = self.env['product.category'].browse(categ_id)
        while categ:
            code = (getattr(categ, 'code', '') or '').strip().upper()
            if code:
                return code
            categ = categ.parent_id
        return ''

    def _normalize_lens_index_cid(self, index):
        raw = (getattr(index, 'cid', '') or '').strip().upper()
        cleaned = ''.join(ch for ch in raw if ch.isalnum())
        if not cleaned:
            raise ValidationError('Chiết suất chưa có CID để sinh mã sản phẩm.')
        if len(cleaned) > 3:
            raise ValidationError(
                f'CID chiết suất "{raw}" không hợp lệ sau chuẩn hóa ({cleaned}), yêu cầu tối đa 3 ký tự.'
            )
        return cleaned.zfill(3)

    def _build_default_code_prefix(self, group_id, brand_id, lens_index_id=False, product_type='lens'):
        group = self.env['product.group'].browse(group_id)
        brand = self.env['product.brand'].browse(brand_id)

        if not group or not group.exists():
            raise ValidationError('Thiếu group_id hợp lệ để sinh mã sản phẩm.')
        if not brand or not brand.exists():
            raise ValidationError('Thiếu brand_id hợp lệ để sinh mã sản phẩm.')

        try:
            group_seq = int(group.sequence)
        except Exception as exc:
            raise ValidationError('STT nhóm (group.sequence) không hợp lệ để sinh mã sản phẩm.') from exc

        try:
            brand_seq = int(brand.sequence)
        except Exception as exc:
            raise ValidationError('STT thương hiệu (brand.sequence) không hợp lệ để sinh mã sản phẩm.') from exc

        if group_seq < 0 or group_seq > 99:
            raise ValidationError('STT nhóm phải nằm trong khoảng 0-99 để tạo AA.')
        if brand_seq < 0 or brand_seq > 999:
            raise ValidationError('STT thương hiệu phải nằm trong khoảng 0-999 để tạo BBB.')

        aa = f"{group_seq:02d}"
        bbb = f"{brand_seq:03d}"

        if product_type == 'lens':
            if not lens_index_id:
                raise ValidationError('Sản phẩm lens thiếu lens_index_id để tạo CCC.')
            lens_index = self.env['product.lens.index'].browse(lens_index_id)
            if not lens_index or not lens_index.exists():
                raise ValidationError('lens_index_id không hợp lệ để tạo CCC.')
            ccc = self._normalize_lens_index_cid(lens_index)
        else:
            ccc = '000'

        return f"{aa}{bbb}{ccc}"

    def _get_max_default_code_suffix(self, prefix):
        max_suffix = -1
        code_len = len(prefix) + self._DEFAULT_CODE_SUFFIX_LEN
        records = self.with_context(active_test=False).search_read(
            [('default_code', 'like', f'{prefix}%')],
            ['default_code'],
        )
        for rec in records:
            code = (rec.get('default_code') or '').strip().upper()
            if len(code) != code_len:
                continue
            suffix = code[-self._DEFAULT_CODE_SUFFIX_LEN:]
            if any(ch not in self._BASE36_ALPHABET for ch in suffix):
                continue
            suffix_value = self._product_code_base36_to_int(suffix)
            if suffix_value > max_suffix:
                max_suffix = suffix_value
        return max_suffix

    def generate_next_default_code(self, group_id, brand_id, lens_index_id=False, product_type='lens', sequence_cache=None):
        cache = sequence_cache if sequence_cache is not None else {}
        prefix = self._build_default_code_prefix(
            group_id,
            brand_id,
            lens_index_id=lens_index_id,
            product_type=product_type,
        )

        current_suffix = cache.get(prefix)
        if current_suffix is None:
            current_suffix = self._get_max_default_code_suffix(prefix)

        next_suffix = current_suffix + 1
        if next_suffix > self._DEFAULT_CODE_SUFFIX_MAX:
            raise ValidationError(
                f'Prefix {prefix} đã vượt giới hạn suffix 5 ký tự base36 (00000..ZZZZZ).'
            )

        cache[prefix] = next_suffix
        suffix_text = self._product_code_int_to_base36(next_suffix, self._DEFAULT_CODE_SUFFIX_LEN)
        return f"{prefix}{suffix_text}"

    def _auto_generate_product_code(self, categ_id, brand_id, lens_index_id=None, group_id=None, sequence_cache=None):
        """Generate product code in format AABBBCCCDDDDD."""
        product_type = 'lens' if self._get_root_category_code_from_id(categ_id) == 'TK' else 'non_lens'
        return self.generate_next_default_code(
            group_id,
            brand_id,
            lens_index_id=lens_index_id,
            product_type=product_type,
            sequence_cache=sequence_cache,
        )

    def write(self, vals):
        self._check_duplicate_name(vals, existing_ids=self.ids)
        if 'categ_id' in vals:
            # Clear groups when category changes, unless caller explicitly sets group fields.
            if not any(k in vals for k in ('lens_group_id', 'opt_group_id', 'acc_group_id', 'group_id')):
                vals.setdefault('lens_group_id', False)
                vals.setdefault('opt_group_id', False)
                vals.setdefault('acc_group_id', False)
                vals.setdefault('group_id', False)
        return super().write(vals)

