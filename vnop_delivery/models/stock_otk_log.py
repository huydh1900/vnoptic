# -*- coding: utf-8 -*-
from odoo import fields, models


class StockOtkLog(models.Model):
    _name = 'stock.otk.log'
    _description = 'Lần OTK'
    _order = 'date desc'

    name = fields.Char(string='Mã OTK', readonly=True)
    sequence = fields.Integer(string='Lần', readonly=True)
    date = fields.Datetime(string='Ngày kiểm', default=fields.Datetime.now, readonly=True)
    picking_id = fields.Many2one('stock.picking', string='Phiếu nhập', readonly=True)
    purchase_id = fields.Many2one('purchase.order', string='Đơn mua hàng', readonly=True, index=True)
    user_id = fields.Many2one('res.users', string='Người kiểm', default=lambda self: self.env.user, readonly=True)
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
    note = fields.Char(string='Ghi chú', readonly=True)
