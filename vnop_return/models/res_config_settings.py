# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    vnop_return_director_threshold = fields.Float(
        string='Ngưỡng Giám đốc duyệt trả hàng',
        config_parameter='vnop_return.director_threshold',
        default=10000000.0,
        help='Phiếu trả ngoại lệ có tổng tiền vượt ngưỡng này sẽ cần Giám đốc duyệt.')
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', readonly=True)
