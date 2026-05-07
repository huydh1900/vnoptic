# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProductPricelistItem(models.Model):
    _name = 'product.pricelist.item'
    _inherit = ['product.pricelist.item', 'mail.thread']

    fixed_price = fields.Float(tracking=True)
    date_start = fields.Datetime(tracking=True)
    date_end = fields.Datetime(tracking=True)

    is_active_now = fields.Boolean(
        string='Đang hiệu lực',
        compute='_compute_is_active_now',
    )

    @api.depends('date_start', 'date_end')
    def _compute_is_active_now(self):
        now = fields.Datetime.now()
        for item in self:
            start_ok = not item.date_start or item.date_start <= now
            end_ok = not item.date_end or item.date_end >= now
            item.is_active_now = start_ok and end_ok
