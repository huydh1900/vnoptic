# -*- coding: utf-8 -*-
from odoo import fields, models


class StockOtkLog(models.Model):
    """Snapshot kết quả mỗi lần OTK — chỉ đọc, phục vụ audit/truy vết.

    Mỗi record = 1 lần bấm "Xác nhận OTK" trên wizard.
    Sequence đếm theo PO để biết PO đã OTK bao nhiêu lần
    (bất kể trên picking gốc hay backorder).
    """
    _name = 'stock.otk.log'
    _description = 'Lần OTK'
    _order = 'date desc'

    name = fields.Char(string='Mã OTK', readonly=True)
    sequence = fields.Integer(string='Lần', readonly=True)
    date = fields.Datetime(string='Ngày kiểm', default=fields.Datetime.now, readonly=True)
    picking_id = fields.Many2one('stock.picking', string='Phiếu nhập', readonly=True)
    purchase_id = fields.Many2one('purchase.order', string='Đơn mua hàng', readonly=True, index=True)
    user_id = fields.Many2one('res.users', string='Người kiểm', default=lambda self: self.env.user, readonly=True)
    # Link đến phiếu điều chuyển tạo bởi OTK lần này, phục vụ truy vết
    transfer_ok_id = fields.Many2one('stock.picking', string='Phiếu chuyển kho đạt', readonly=True)
    transfer_ng_id = fields.Many2one('stock.picking', string='Phiếu chuyển kho lỗi', readonly=True)
    line_ids = fields.One2many('stock.otk.log.line', 'log_id', string='Chi tiết')


class StockOtkLogLine(models.Model):
    _name = 'stock.otk.log.line'
    _description = 'Chi tiết lần OTK'

    log_id = fields.Many2one('stock.otk.log', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Sản phẩm', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='ĐVT', readonly=True)
    qty_demand = fields.Float(string='SL yêu cầu', readonly=True)
    qty_otk = fields.Float(string='SL kiểm', readonly=True)
    qty_ok = fields.Float(string='SL đạt', readonly=True)
    qty_ng = fields.Float(string='SL không đạt', readonly=True)
    qty_remaining = fields.Float(string='SL dư', readonly=True)
    # SP ngoài PO: NCC giao nhầm/giao thêm, không có trong PO gốc
    is_extra = fields.Boolean(string='SP ngoài PO', readonly=True)
    # Chỉ có giá trị khi is_extra=True: 'accept' đã nhận vào kho, 'return' tạo phiếu trả NCC
    action_type = fields.Selection([
        ('accept', 'Nhận vào kho'),
        ('return', 'Trả NCC'),
    ], string='Xử lý', readonly=True)
    note = fields.Char(string='Ghi chú', readonly=True)
