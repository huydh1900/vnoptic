# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    order_request_id = fields.Many2one(
        'vnop.order.request', string='Đơn yêu cầu B2B',
        copy=False, index=True, ondelete='set null',
    )
