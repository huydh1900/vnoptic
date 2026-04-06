# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    channel_type = fields.Selection(
        selection=[
            ('wholesale', 'Bán buôn'),
            ('retail', 'Bán lẻ'),
        ],
        string='Kênh bán',
        compute='_compute_channel_type',
        store=True,
        readonly=False,
        precompute=True,
        help='Kênh bán của đơn hàng. Mặc định lấy từ khách hàng, có thể chỉnh tay.',
    )

    @api.depends('partner_id')
    def _compute_channel_type(self):
        for order in self:
            if order.partner_id and order.partner_id.channel_type:
                order.channel_type = order.partner_id.channel_type
            elif not order.channel_type:
                order.channel_type = 'retail'
