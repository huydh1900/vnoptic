# -*- coding: utf-8 -*-
from odoo import fields, models


class DeliveryScheduleLine(models.Model):
    _name = 'delivery.schedule.line'
    _description = 'Chi tiết hàng giao'
    _order = 'id'

    schedule_id = fields.Many2one('delivery.schedule', ondelete='cascade', index=True, required=True)
    contract_line_id = fields.Many2one(
        'contract.line',
        string='Dòng hợp đồng',
        domain="[('contract_id', '=', parent.contract_id)]",
        required=True,
    )
    purchase_offer_id = fields.Many2one(
        'purchase.offer',
        string='Mã ĐNMH',
        related='contract_line_id.purchase_offer_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Sản phẩm',
        related='contract_line_id.product_id',
        store=True,
        readonly=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='ĐVT',
        related='contract_line_id.uom_id',
        store=True,
        readonly=True,
    )
    qty_contract = fields.Float(
        string='SL hợp đồng',
        digits='Product Unit of Measure',
        related='contract_line_id.product_qty',
        store=True,
        readonly=True,
    )
    qty_planned = fields.Float(string='SL dự kiến', digits='Product Unit of Measure')
    price_unit = fields.Float(
        string='Đơn giá', digits='Product Price',
        related='contract_line_id.price_unit', store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='contract_line_id.currency_id', store=True,
    )
    qty_received = fields.Float(string='Đã nhận', digits='Product Unit of Measure', default=0.0)
