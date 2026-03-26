# -*- coding: utf-8 -*-
from odoo import models, fields

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'
    
    # Phân loại kho: 1 = Đạt, 2 = Lỗi
    warehouse_type = fields.Selection([
        ('1', 'Đạt'),
        ('2', 'Lỗi'),
    ], string='Phân loại kho', default='1', help='Chọn loại kho: Đạt hoặc Lỗi')
