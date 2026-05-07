# -*- coding: utf-8 -*-
from odoo import fields, models


class DealerTier(models.Model):
    _inherit = 'dealer.tier'

    claim_pct = fields.Float(
        string='% Claim back',
        default=5.0,
        help='Tỷ lệ % claim back tính trên đơn giá saleout',
    )
