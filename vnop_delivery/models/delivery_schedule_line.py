# -*- coding: utf-8 -*-
from odoo import api, fields, models


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
    qty_planned = fields.Float(string='SL dự kiến', digits='Product Unit of Measure')
    qty_received = fields.Float(
        string='SL về', digits='Product Unit of Measure',
        related='contract_line_id.qty_received', store=True,
    )
