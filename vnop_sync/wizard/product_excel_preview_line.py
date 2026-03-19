# -*- coding: utf-8 -*-

from odoo import models, fields

class ProductExcelPreviewLine(models.TransientModel):
    _name = 'product.excel.preview.line'
    _description = 'Excel Import Preview Line'
    _order = 'row_number'
    
    wizard_id = fields.Many2one('product.excel.import', string='Wizard', required=True, ondelete='cascade')
    row_number = fields.Integer('Row #', readonly=True)
    
    # Common fields
    group = fields.Char('Group', readonly=True)
    image = fields.Binary('Image', readonly=True)
    full_name = fields.Char('FullName', readonly=True)
    eng_name = fields.Char('EngName', readonly=True)
    trade_name = fields.Char('TradeName', readonly=True)
    unit = fields.Char('Unit', readonly=True)
    brand = fields.Char('TradeMark', readonly=True)
    supplier = fields.Char('Supplier', readonly=True)
    country = fields.Char('Country', readonly=True)
    supplier_warranty = fields.Char('Supplier_Warranty', readonly=True)
    warranty = fields.Char('Warranty', readonly=True)
    warranty_retail = fields.Char('Warranty_Retail', readonly=True)
    accessory = fields.Char('Accessory', readonly=True)
    origin_price = fields.Float('Origin_Price', readonly=True)
    currency = fields.Char('Currency', readonly=True)
    
    # Auto-generated code
    generated_code = fields.Char('Mã tự động', readonly=True, help='Mã sẽ được sinh tự động khi import')
    
    retail_price = fields.Float('Giá lẻ', readonly=True)
    wholesale_price = fields.Float('Giá sỉ', readonly=True)
    cost_price = fields.Float('Giá vốn', readonly=True)
    wholesale_price_max = fields.Float('Wholesale_Price_Max', readonly=True)
    wholesale_price_min = fields.Float('Wholesale_Price_Min', readonly=True)
    use = fields.Text('Use', readonly=True)
    guide = fields.Text('Guide', readonly=True)
    warning = fields.Text('Warning', readonly=True)
    preserve = fields.Text('Preserve', readonly=True)
    description = fields.Text('Description', readonly=True)
    note = fields.Text('Note', readonly=True)
    
    # Lens fields
    sph = fields.Char('SPH', readonly=True)
    cyl = fields.Char('CYL', readonly=True)
    add = fields.Char('ADD', readonly=True)
    axis = fields.Char('AXIS', readonly=True)
    prism = fields.Char('PRISM', readonly=True)
    prismbase = fields.Char('PRISMBASE', readonly=True)
    lens_base = fields.Char('BASE', readonly=True)
    abbe = fields.Char('Abbe', readonly=True)
    polarized = fields.Char('Polarized', readonly=True)
    diameter = fields.Char('Diameter', readonly=True)
    design1 = fields.Char('Design 1', readonly=True)
    design2 = fields.Char('Design 2', readonly=True)
    lens_material = fields.Char('Material', readonly=True)
    index = fields.Char('Index', readonly=True)
    uv = fields.Char('Uv', readonly=True)
    lens_coating = fields.Char('Coating', readonly=True)
    hmc = fields.Char('HMC', readonly=True)
    pho = fields.Char('PHO', readonly=True)
    tind = fields.Char('TIND', readonly=True)
    color_int = fields.Char('ColorInt', readonly=True)
    corridor = fields.Char('Corridor', readonly=True)
    mir_coating = fields.Char('MirCoating', readonly=True)
    
    # Optical fields
    sku = fields.Char('SKU', readonly=True)
    model = fields.Char('Model', readonly=True)
    model_supplier = fields.Char('Model_Supplier', readonly=True)
    serial = fields.Char('Serial', readonly=True)
    color_code = fields.Char('Color_Code', readonly=True)
    season = fields.Char('Season', readonly=True)
    frame = fields.Char('Frame', readonly=True)
    gender = fields.Char('Gender', readonly=True)
    frame_type = fields.Char('Frame_Type', readonly=True)
    opt_shape = fields.Char('Shape', readonly=True)
    ve = fields.Char('Ve', readonly=True)
    temple = fields.Char('Temple', readonly=True)
    material_ve = fields.Char('Material_Ve', readonly=True)
    material_temple_tip = fields.Char('Material_TempleTip', readonly=True)
    material_lens = fields.Char('Material_Lens', readonly=True)
    material_opt_front = fields.Char('Material_Opt_Front', readonly=True)
    material_opt_temple = fields.Char('Material_Opt_Temple', readonly=True)
    color_lens = fields.Char('Color_Lens', readonly=True)
    opt_coating = fields.Char('Coating', readonly=True)
    color_opt_front = fields.Char('Color_Opt_Front', readonly=True)
    color_opt_temple = fields.Char('Color_Opt_Temple', readonly=True)
    lens_width = fields.Char('Lens Width', readonly=True)
    bridge_width = fields.Char('Bridge Width', readonly=True)
    temple_width = fields.Char('Temple Width', readonly=True)
    lens_height = fields.Char('Lens Height', readonly=True)
    lens_span = fields.Char('Lens Span', readonly=True)

    # Accessory fields
    design = fields.Char('Design', readonly=True)
    accessory_shape = fields.Char('Shape', readonly=True)
    accessory_material = fields.Char('Material', readonly=True)
    accessory_color = fields.Char('Color', readonly=True)
    width = fields.Char('Width', readonly=True)
    length = fields.Char('Length', readonly=True)
    height = fields.Char('Height', readonly=True)
    head = fields.Char('Head', readonly=True)
    body = fields.Char('Body', readonly=True)
    
    # Validation
    has_error = fields.Boolean('Có lỗi', readonly=True, default=False)
    error_message = fields.Text('Thông báo lỗi', readonly=True)
