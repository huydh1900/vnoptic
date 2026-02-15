# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Đợt giao',
        ondelete='set null',
        index=True,
    )
