import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.addons.vnoptic_product import utils as vnoptic_utils

_logger = logging.getLogger(__name__)


class ProductCreationWizard(models.TransientModel):
    _name = 'product.creation.wizard'
    _description = 'VNOPTIC Product Creation Wizard'

    product_type = fields.Selection([
        ('lens', 'Lens'),
        ('opt', 'Optical'),
        ('accessory', 'Accessory')
    ], string='Loại sản phẩm', required=True)

    group_id = fields.Many2one('product.group', string='Nhóm')

    cid = fields.Char('Ký hiệu viết tắt')
    image_1920 = fields.Binary("Ảnh sản phẩm")
    name = fields.Char('Tên đầy đủ', required=True)
    eng_name = fields.Char('Tên Tiếng Anh', required=True)
    trade_name = fields.Char('Tên Thương mại')
    unit = fields.Char('Đơn vị', default='Chiếc')
    supplier_id = fields.Many2one('res.partner', string='Nhà cung cấp')
    country_id = fields.Many2one('xnk.country', string='Xuất xứ')
    description = fields.Text('Mô tả')
    uses = fields.Text('Công dụng')
    guide = fields.Text('Hướng dẫn sử dụng')
    warning = fields.Text('Cảnh báo')
    preserve = fields.Text('Bảo quản')
    # Price fields from JSON API - using x_ prefix to match xnk_intergration
    rt_price = fields.Float('Giá bán lẻ (Retail Price)')  # Maps to list_price
    x_ws_price = fields.Float('Giá sỉ (Wholesale Price)')
    x_ct_price = fields.Float('Giá vốn (Cost Price)')
    x_or_price = fields.Float('Giá nguyên tệ (Original Price)')
    x_ws_price_max = fields.Float('Giá sỉ tối đa')
    x_ws_price_min = fields.Float('Giá sỉ tối thiểu')
    
    # Tax and currency
    x_tax_percent = fields.Float('Thuế (%)')
    currency_selection = fields.Selection([
        ('vnd', 'VND'),
        ('usd', 'USD'),
        ('japan', 'Japan (YÊN)'),
        ('china', 'China (TỆ)')
    ], string='Đơn vị ngoại tệ', default='vnd')
    x_currency_zone_value = fields.Float('Tỉ giá (Exchange Rate)', default=1.0)
    currency_id = fields.Many2one('res.currency', string='Đơn vị nguyên tệ')
    currency_zone_id = fields.Many2one('res.currency', string='Khu vực tiền tệ')
    
    # Warranty fields - multiple types from JSON API
    warranty_id = fields.Many2one('xnk.warranty', string='Bảo hành chính')
    warranty_detail_id = fields.Many2one('xnk.warranty', string='Bảo hành chi tiết')
    warranty_retail_id = fields.Many2one('xnk.warranty', string='Bảo hành bán lẻ')
    warranty_supplier_id = fields.Many2one('xnk.warranty', string='Bảo hành hãng')
    
    # Legacy text fields (kept for backward compatibility)
    warranty_supplier = fields.Text('Bảo hành hãng (text)')
    warranty_company = fields.Text('Bảo hành công ty (text)')
    warranty_retail = fields.Text('Bảo hành bán lẻ (text)')
    
    # Other fields
    brand_id = fields.Many2one('xnk.brand', string='Thương hiệu')
    status_product_id = fields.Many2one('product.status', string='Trạng thái sản phẩm')

    sph = fields.Char('SPH')
    cyl = fields.Char('CYL')
    diameter = fields.Char('Đường kính')
    prism = fields.Char('Prism')
    len_add = fields.Char('ADD')
    base = fields.Char('Base Curve')
    design1_id = fields.Many2one('product.design', string='Thiết kế 1')
    design2_id = fields.Many2one('product.design', string='Thiết kế 2')
    material_id = fields.Many2one('product.material', string='Vật liệu')
    index_id = fields.Many2one('product.lens.index', string='Chiết suất')
    uv_id = fields.Many2one('product.uv', string='UV')
    cl_pho_id = fields.Many2one('product.cl', string='Pho Col')
    cl_hmc_id = fields.Many2one('product.cl', string='HMC')
    cl_tint_id = fields.Many2one('product.cl', string='Tint Col')
    color_int = fields.Char('Độ đậm màu', size=50)
    mir_coating = fields.Char('Màu tráng gương', size=50)
    coating_ids = fields.Many2many('product.coating', 'wiz_coating_rel', string='Coating')

    season = fields.Char('Season')
    sku = fields.Char('SKU')
    model_name = fields.Char('Model')
    serial = fields.Char('Serial')
    color_code = fields.Char('Color Code')
    original_code = fields.Char('Mã gốc')

    # OPT specific fields - Many2one to lookup tables
    frame_id = fields.Many2one('product.frame', string='Kiểu gọng')
    frame_type_id = fields.Many2one('product.frame.type', string='Loại gọng')
    ve_id = fields.Many2one('product.ve', string='Ve')
    shape_id = fields.Many2one('product.shape', string='Kiểu dáng mặt kính')
    temple_id = fields.Many2one('product.temple', string='Chuôi càng')
    gender = fields.Selection([('1', 'Nam'), ('2', 'Nữ'), ('3', 'Unisex')], 'Giới tính')

    material_front_ids = fields.Many2many(
        'product.material', 'wiz_material_front_rel', 'wizard_id', 'material_id', string='Mặt trước')
    material_temple_ids = fields.Many2many(
        'product.material', 'wiz_material_temple_rel', 'wizard_id', 'material_id', string='Càng')
    material_temple_tip_id = fields.Many2one('product.material', string='Chuôi càng')
    material_lens_id = fields.Many2one('product.material', string='Mắt kính')
    material_ve_id = fields.Many2one('product.material', string='Ve kính')
    coating_opt = fields.Many2one('product.coating', string='Lớp mạ')

    color_front_id = fields.Many2one('product.cl', string='Màu mặt trước')
    color_temple_id = fields.Many2one('product.cl', string='Màu càng kính')
    color_lens_id = fields.Many2one('product.cl', string='Màu mắt kính')

    temple_width = fields.Integer('Dài gọng')
    lens_height = fields.Integer('Cao mắt')
    lens_width = fields.Integer('Dài mắt')
    bridge_width = fields.Integer('Dài cầu')
    lens_span = fields.Integer('Ngang mắt')


    @api.model
    def default_get(self, fields_list):
        _logger.info("=" * 60)
        _logger.info(f"default_get called")

        res = super().default_get(fields_list)

        # Set unit mặc định
        res['unit'] = 'Chiếc'

        # LẶP QUA TẤT CẢ FIELD và kiểm tra giá trị
        for fname in fields_list:
            field = self._fields.get(fname)
            if not field:
                continue

            if isinstance(field, fields.Many2one):
                current_val = res.get(fname)

                if current_val and not isinstance(current_val, (bool, int)):
                    _logger.error(f"❌❌❌ FOUND _UNKNOWN IN default_get! ❌❌❌")
                    _logger.error(f"   Field: {fname}")
                    _logger.error(f"   Value: {current_val}")
                    _logger.error(f"   Type: {type(current_val)}")

                    # Set về False
                    res[fname] = False
                else:
                    # Force set tất cả Many2one = False
                    res[fname] = False

        # Force set Many2many = empty
        for fname, field in self._fields.items():
            if isinstance(field, fields.Many2many) and fname in fields_list:
                res[fname] = [(6, 0, [])]

        _logger.info(f"Final res keys: {list(res.keys())}")
        _logger.info("=" * 60)

        return res

    @api.onchange('product_type')
    def _onchange_product_type(self):
        _logger.info("=" * 60)
        _logger.info(f"_onchange_product_type triggered: {self.product_type}")

        result = {}
        if self.product_type:
            group_type_mapping = {
                'lens': 'Mắt',
                'opt': 'Gọng',
                'accessory': 'Khác'
            }
            
            group_type_name = group_type_mapping.get(self.product_type)
            if group_type_name:
                group_type = self.env['product.group.type'].sudo().search([
                    ('name', '=', group_type_name)
                ], limit=1)
                
                if group_type:
                    result['domain'] = {'group_id': [('group_type_id', '=', group_type.id)]}
                else:
                    result['domain'] = {'group_id': []}
            else:
                result['domain'] = {'group_id': []}

        # Reset fields
        if self.product_type:
            try:
                # Lấy danh sách tất cả Many2one fields
                many2one_fields = []
                for fname, field in self._fields.items():
                    if isinstance(field, fields.Many2one):
                        many2one_fields.append(fname)

                _logger.info(f"Found {len(many2one_fields)} Many2one fields")

                # Reset từng field và bắt lỗi
                for fname in many2one_fields:
                    try:
                        current_value = getattr(self, fname, None)

                        # Kiểm tra nếu là _unknown
                        if current_value and str(type(current_value)) == "lass '_unknown'>":
                            _logger.error(f"❌❌❌ Field '{fname}' is _unknown! ❌❌❌")
                            _logger.error(f"   Value: {current_value}")
                            _logger.error(f"   Type: {type(current_value)}")

                        # Nếu value có id → log
                        if current_value and hasattr(current_value, 'id'):
                            _logger.info(f"Field {fname}: id={current_value.id}, name={current_value.display_name}")

                        # Reset về False
                        setattr(self, fname, False)
                        _logger.info(f"✅ Reset {fname} = False")

                    except Exception as e:
                        _logger.error(f"❌ Error with field {fname}: {e}", exc_info=True)

                # Reset Many2many
                self.coating_ids = [(6, 0, [])]
                self.material_front_ids = [(6, 0, [])]
                self.material_temple_ids = [(6, 0, [])]

                _logger.info("✅ All fields reset successfully")

            except Exception as e:
                _logger.exception(f"❌ Error in _onchange_product_type: {e}")

        _logger.info("=" * 60)
        
        return result


    @api.onchange('group_id', 'brand_id', 'index_id')
    def _onchange_generate_code(self):
        
        if self.group_id or self.brand_id or self.index_id:
            code = vnoptic_utils.product_code_utils.generate_product_code(
                self.env,
                self.group_id.id if self.group_id else False,
                self.brand_id.id if self.brand_id else False,
                self.index_id.id if self.index_id else False
            )
            self.cid = code
    
    @api.onchange('currency_selection')
    def _onchange_currency_selection(self):
        if self.currency_selection:
            currency_map = {
                'vnd': 'VND',
                'usd': 'USD',
                'japan': 'JPY',
                'china': 'CNY'
            }
            currency_code = currency_map.get(self.currency_selection)
            if currency_code:
                currency = self.env['res.currency'].sudo().search([('name', '=', currency_code)], limit=1)
                if currency:
                    self.currency_zone_id = currency.id
                    # Gợi ý tỉ giá mặc định nếu cần (ví dụ: VND là 1)
                    if self.currency_selection == 'vnd':
                        self.x_currency_zone_value = 1.0

    @api.onchange('design_id')
    def _onchange_design_id(self):
        """Populate optical fields from selected design"""
        if self.design_id and self.design_id.design_type == 'opt':
            self.frame = self.design_id.frame or ''
            self.frame_type = self.design_id.frame_type or ''
            self.shape = self.design_id.shape or ''
            self.ve = self.design_id.ve or ''
            self.temple = self.design_id.temple or ''


    def action_create_product(self):
        self.ensure_one()

        _logger.info("=" * 80)
        _logger.info(f"Creating product: {self.name}")
        _logger.info(f"Product type: {self.product_type}")

        # Validate
        if not self.name or not self.eng_name:
            raise UserError("Vui lòng nhập tên sản phẩm và tên tiếng Anh!")

        if not self.cid:
            code = vnoptic_utils.product_code_utils.generate_product_code(
                self.env,
                self.group_id.id if self.group_id else False,
                self.brand_id.id if self.brand_id else False,
                self.index_id.id if self.index_id else False
            )
            self.cid = code

        # Chuẩn bị data chung cho product.template
        # Chuẩn bị data chung cho product.template
        # Tìm hoặc tạo thuế dựa trên phần trăm
        tax_id = False
        if self.x_tax_percent:
            tax_name = f"Tax {self.x_tax_percent}%"
            tax = self.env['account.tax'].sudo().search([
                ('name', '=', tax_name),
                ('type_tax_use', '=', 'sale')
            ], limit=1)
            if not tax:
                tax = self.env['account.tax'].sudo().create({
                    'name': tax_name,
                    'amount': self.x_tax_percent,
                    'amount_type': 'percent',
                    'type_tax_use': 'sale'
                })
            tax_id = tax.id

        vals = {
            'name': self.name,
            'default_code': self.cid or '',
            'product_type': self.product_type,
            'type': 'product',  # Stockable product
            'categ_id': self._get_category_id(),
            
            # Price fields
            'list_price': self.rt_price or 0.0,  # Retail price = Sales Price
            'standard_price': (self.x_or_price or 0.0) * (self.x_currency_zone_value or 1.0),  # Cost price quy đổi sang VND
            'x_ws_price': self.x_ws_price or 0.0,
            'x_ct_price': self.x_ct_price or 0.0,
            'x_or_price': self.x_or_price or 0.0,
            'x_ws_price_max': self.x_ws_price_max or 0.0,
            'x_ws_price_min': self.x_ws_price_min or 0.0,
            
            # Tax
            'x_tax_percent': self.x_tax_percent or 0.0,
            'taxes_id': [(6, 0, [tax_id])] if tax_id else False,
            
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'uom_po_id': self.env.ref('uom.product_uom_unit').id,
            'sale_ok': True,
            'purchase_ok': True,
            'active': True,
            'image_1920': self.image_1920,

            # Thông tin thương hiệu/NCC/Xuất xứ
            'brand_id': self.brand_id.id if self.brand_id else False,
            'supplier_id': self.supplier_id.id if self.supplier_id else False,
            'country_id': self.country_id.id if self.country_id else False,
            'group_id': self.group_id.id if self.group_id else False,
            
            # Warranty fields
            'warranty_id': self.warranty_id.id if self.warranty_id else False,
            
            # Status
            'status_product_id': self.status_product_id.id if self.status_product_id else False,
            
            # Currency
            'currency_zone_id': self.currency_zone_id.id if self.currency_zone_id else False,
            'x_currency_zone_code': self.currency_zone_id.name if self.currency_zone_id else '',
            'x_currency_zone_value': self.x_currency_zone_value or 1.0,
            
            # Unit and other info
            'unit': self.unit or 'Chiếc',
            'eng_name': self.eng_name,
            'x_eng_name': self.eng_name,
            'trade_name': self.trade_name,
            'x_trade_name': self.trade_name,
            'uses': self.uses or '',
            'x_uses': self.uses or '',
            'guide': self.guide or '',
            'x_guide': self.guide or '',
            'warning': self.warning or '',
            'x_warning': self.warning or '',
            'preserve': self.preserve or '',
            'x_preserve': self.preserve or '',

            # Mô tả
            'description': self.description or '',
            'x_note_long': self.description or '',
            'description_sale': self.uses or '',
        }

        # Tạo product template
        product = self.env['product.template'].create(vals)

        # Tạo bản ghi riêng cho Lens hoặc OPT
        if self.product_type == 'lens':
            self._create_lens_record(product)
        elif self.product_type == 'opt':
            self._create_opt_record(product)

        _logger.info(f"✅ Product created: ID={product.id}, Name={product.name}")
        _logger.info("=" * 80)

        # Redirect về product vừa tạo
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sản phẩm vừa tạo',
            'res_model': 'product.template',
            'res_id': product.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _get_category_id(self):
        category_mapping = {
            'lens': 'Lens',
            'opt': 'Optical Frame',
            'accessory': 'Accessory'
        }

        category_name = category_mapping.get(self.product_type, 'All')
        category = self.env['product.category'].search([('name', '=', category_name)], limit=1)

        if not category:
            category = self.env['product.category'].create({'name': category_name})

        return category.id

    def _create_lens_record(self, product):
        vals = {
            'product_tmpl_id': product.id,
            'sph': self.sph or '',
            'cyl': self.cyl or '',
            'diameter': self.diameter or '',
            'prism': self.prism or '',
            'len_add': self.len_add or '',
            'base': self.base or '',
            'design1_id': self.design1_id.id if self.design1_id else False,
            'design2_id': self.design2_id.id if self.design2_id else False,
            'material_id': self.material_id.id if self.material_id else False,
            'index_id': self.index_id.id if self.index_id else False,
            'uv_id': self.uv_id.id if self.uv_id else False,
            'cl_pho_id': self.cl_pho_id.id if self.cl_pho_id else False,
            'cl_hmc_id': self.cl_hmc_id.id if self.cl_hmc_id else False,
            'cl_tint_id': self.cl_tint_id.id if self.cl_tint_id else False,
            'color_int': self.color_int or '',
            'mir_coating': self.mir_coating or '',
            'coating_ids': [(6, 0, self.coating_ids.ids)] if self.coating_ids else [(6, 0, [])],
        }

        self.env['product.lens'].create(vals)
        _logger.info(f"✅ Lens record created for product {product.id}")

    def _create_opt_record(self, product):
        vals = {
            'product_tmpl_id': product.id,
            'season': self.season or '',
            'sku': self.sku or '',
            'model_name': self.model_name or '',
            'serial': self.serial or '',
            'frame_type_id': self.frame_type_id.id if self.frame_type_id else False,
            'gender': self.gender or '',
            'frame_id': self.frame_id.id if self.frame_id else False,
            've_id': self.ve_id.id if self.ve_id else False,
            'shape_id': self.shape_id.id if self.shape_id else False,
            'temple_id': self.temple_id.id if self.temple_id else False,
            'material_front_ids': [(6, 0, self.material_front_ids.ids)] if self.material_front_ids else [(6, 0, [])],
            'material_temple_ids': [(6, 0, self.material_temple_ids.ids)] if self.material_temple_ids else [(6, 0, [])],
            'material_temple_tip_id': self.material_temple_tip_id.id if self.material_temple_tip_id else False,
            'material_lens_id': self.material_lens_id.id if self.material_lens_id else False,
            'material_ve_id': self.material_ve_id.id if self.material_ve_id else False,
            'color_front_id': self.color_front_id.id if self.color_front_id else False,
            'color_lens_id': self.color_lens_id.id if self.color_lens_id else False,
            'color_temple_id': self.color_temple_id.id if self.color_temple_id else False,
            'temple_width': self.temple_width or 0,
            'lens_height': self.lens_height or 0,
            'lens_width': self.lens_width or 0,
            'bridge_width': self.bridge_width or 0,
            'lens_span': self.lens_span or 0,
        }

        self.env['product.opt'].create(vals)
        _logger.info(f"✅ OPT record created for product {product.id}")

    def action_create_design1(self):
        self.ensure_one()

        return {
            'name': 'Thêm Thiết Kế Mới',
            'type': 'ir.actions.act_window',
            'res_model': 'product.design',
            'view_mode': 'form',
            'view_id': self.env.ref('vnoptic_product.view_product_design_form_quick').id,
            'target': 'new',
            'context': {
                'default_active': True,
                'dialog_size': 'medium',
            }
        }

    def action_create_design2(self):
        return self.action_create_design1()  # Dùng chung logic
