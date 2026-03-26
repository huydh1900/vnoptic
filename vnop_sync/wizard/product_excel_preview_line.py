# -*- coding: utf-8 -*-

from odoo import models, fields

class ProductExcelPreviewLine(models.TransientModel):
    _name = 'product.excel.preview.line'
    _description = 'Dòng dữ liệu xem trước import Excel'
    _order = 'row_number'
    
    wizard_id = fields.Many2one('product.excel.import', string='Phiên import', required=True, ondelete='cascade')
    product_type = fields.Selection(
        related='wizard_id.product_type',
        string='Loại sản phẩm',
        readonly=True,
    )
    row_number = fields.Integer('Dòng #', readonly=True)
    
    # Common fields
    group = fields.Char('Nhóm sản phẩm', readonly=True)
    image = fields.Binary('Hình ảnh', readonly=True)
    full_name = fields.Char('Tên sản phẩm', readonly=True)
    eng_name = fields.Char('Tên tiếng Anh', readonly=True)
    trade_name = fields.Char('Tên thương mại', readonly=True)
    unit = fields.Char('Đơn vị tính', readonly=True)
    brand = fields.Char('Thương hiệu', readonly=True)
    supplier = fields.Char('Nhà cung cấp', readonly=True)
    country = fields.Char('Quốc gia', readonly=True)
    supplier_warranty = fields.Char('Bảo hành NCC', readonly=True)
    warranty = fields.Char('Bảo hành công ty', readonly=True)
    warranty_retail = fields.Char('Bảo hành bán lẻ', readonly=True)
    accessory = fields.Char('Phụ kiện', readonly=True)
    origin_price = fields.Float('Giá gốc', readonly=True)
    currency = fields.Char('Tiền tệ', readonly=True)
    
    # Auto-generated code
    generated_code = fields.Char('Mã tự động', readonly=True, help='Mã sẽ được sinh tự động khi import')
    
    retail_price = fields.Float('Giá lẻ', readonly=True)
    wholesale_price = fields.Float('Giá sỉ', readonly=True)
    cost_price = fields.Float('Giá vốn', readonly=True)
    wholesale_price_max = fields.Float('Giá sỉ tối đa', readonly=True)
    wholesale_price_min = fields.Float('Giá sỉ tối thiểu', readonly=True)
    use = fields.Text('Công dụng', readonly=True)
    guide = fields.Text('Hướng dẫn', readonly=True)
    warning = fields.Text('Cảnh báo', readonly=True)
    preserve = fields.Text('Bảo quản', readonly=True)
    description = fields.Text('Mô tả', readonly=True)
    note = fields.Text('Ghi chú', readonly=True)
    
    # Lens fields
    sph = fields.Char('SPH', readonly=True)
    cyl = fields.Char('CYL', readonly=True)
    add = fields.Char('ADD', readonly=True)
    axis = fields.Char('AXIS', readonly=True)
    prism = fields.Char('PRISM', readonly=True)
    prismbase = fields.Char('PRISMBASE', readonly=True)
    lens_base = fields.Char('BASE', readonly=True)
    abbe = fields.Char('Abbe', readonly=True)
    polarized = fields.Char('Phân cực', readonly=True)
    diameter = fields.Char('Đường kính', readonly=True)
    design1 = fields.Char('Thiết kế 1', readonly=True)
    design2 = fields.Char('Thiết kế 2', readonly=True)
    lens_material = fields.Char('Chất liệu', readonly=True)
    index = fields.Char('Chiết suất', readonly=True)
    uv = fields.Char('UV', readonly=True)
    lens_coating = fields.Char('Lớp phủ', readonly=True)
    hmc = fields.Char('HMC', readonly=True)
    pho = fields.Char('PHO', readonly=True)
    tind = fields.Char('TIND', readonly=True)
    color_int = fields.Char('Độ đậm màu', readonly=True)
    corridor = fields.Char('Hành lang nhìn', readonly=True)
    mir_coating = fields.Char('Lớp phủ gương', readonly=True)
    
    # Optical fields
    sku = fields.Char('SKU', readonly=True)
    model = fields.Char('Model', readonly=True)
    model_supplier = fields.Char('Model NCC', readonly=True)
    serial = fields.Char('Serial', readonly=True)
    color_code = fields.Char('Mã màu', readonly=True)
    season = fields.Char('Mùa', readonly=True)
    frame = fields.Char('Dáng gọng', readonly=True)
    gender = fields.Char('Giới tính', readonly=True)
    frame_type = fields.Char('Loại gọng', readonly=True)
    opt_shape = fields.Char('Dáng', readonly=True)
    ve = fields.Char('Ve', readonly=True)
    temple = fields.Char('Temple', readonly=True)
    material_ve = fields.Char('Chất liệu ve', readonly=True)
    material_temple_tip = fields.Char('Chất liệu đuôi càng', readonly=True)
    material_lens = fields.Char('Chất liệu tròng', readonly=True)
    material_opt_front = fields.Char('Chất liệu mặt trước', readonly=True)
    material_opt_temple = fields.Char('Chất liệu càng', readonly=True)
    color_lens = fields.Char('Màu tròng', readonly=True)
    opt_coating = fields.Char('Lớp phủ', readonly=True)
    color_opt_front = fields.Char('Màu mặt trước', readonly=True)
    color_opt_temple = fields.Char('Màu càng', readonly=True)
    lens_width = fields.Char('Rộng tròng', readonly=True)
    bridge_width = fields.Char('Rộng cầu', readonly=True)
    temple_width = fields.Char('Dài càng', readonly=True)
    lens_height = fields.Char('Cao tròng', readonly=True)
    lens_span = fields.Char('Độ rộng kính', readonly=True)

    # Accessory fields
    design = fields.Char('Thiết kế', readonly=True)
    accessory_shape = fields.Char('Dáng', readonly=True)
    accessory_material = fields.Char('Chất liệu', readonly=True)
    accessory_color = fields.Char('Màu sắc', readonly=True)
    width = fields.Char('Chiều rộng', readonly=True)
    length = fields.Char('Chiều dài', readonly=True)
    height = fields.Char('Chiều cao', readonly=True)
    head = fields.Char('Đầu', readonly=True)
    body = fields.Char('Thân', readonly=True)
    
    # Validation
    has_error = fields.Boolean('Có lỗi', readonly=True, default=False)
    error_message = fields.Text('Thông báo lỗi', readonly=True)
