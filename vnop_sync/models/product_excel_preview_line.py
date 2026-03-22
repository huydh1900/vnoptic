# -*- coding: utf-8 -*-

from odoo import models, fields

class ProductExcelPreviewLine(models.TransientModel):
    _name = 'product.excel.preview.line'
    _description = 'Excel Import Preview Line'
    _order = 'row_number'
    
    wizard_id = fields.Many2one('product.excel.import', string='Wizard', required=True, ondelete='cascade')
    row_number = fields.Integer('Row #', readonly=True)
    
    # Common fields
    full_name = fields.Char('Tên đầy đủ', readonly=True)
    eng_name = fields.Char('Tên Tiếng Anh', readonly=True)
    trade_name = fields.Char('Tên thương mại', readonly=True)
    group = fields.Char('Nhóm', readonly=True)
    brand = fields.Char('Thương hiệu', readonly=True)
    
    # Auto-generated code
    generated_code = fields.Char('Mã tự động', readonly=True, help='Mã sẽ được sinh tự động khi import')
    
    # Prices
    retail_price = fields.Float('Giá lẻ', readonly=True)
    wholesale_price = fields.Float('Giá sỉ', readonly=True)
    cost_price = fields.Float('Giá vốn', readonly=True)
    
    # Lens specific
    index = fields.Char('Chiết suất', readonly=True)
    design1 = fields.Char('Design 1', readonly=True)
    material = fields.Char('Vật liệu', readonly=True)
    
    # Optical specific
    sku = fields.Char('SKU', readonly=True)
    model = fields.Char('Model', readonly=True)
    frame_type = fields.Char('Kiểu gọng', readonly=True)
    
    # Validation
    has_error = fields.Boolean('Có lỗi', readonly=True, default=False)
    error_message = fields.Text('Thông báo lỗi', readonly=True)
