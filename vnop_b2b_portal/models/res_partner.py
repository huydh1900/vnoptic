# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_b2b_portal_active = fields.Boolean(
        string='Bật cổng B2B',
        default=False,
        help='Cho phép đại lý đăng nhập cổng B2B',
    )
