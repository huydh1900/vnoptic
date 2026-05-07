# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    workflow_approval_l1_threshold = fields.Monetary(
        string='Ngưỡng duyệt L1 (quản lý)',
        default=50000000.0,
        help='Tổng đơn hàng vượt ngưỡng này cần duyệt cấp Quản lý.',
    )
    workflow_approval_l2_threshold = fields.Monetary(
        string='Ngưỡng duyệt L2 (giám đốc)',
        default=200000000.0,
        help='Tổng đơn hàng vượt ngưỡng này cần duyệt cấp Giám đốc.',
    )
    discount_approval_l1_threshold = fields.Float(
        string='Ngưỡng chiết khấu L1 (%)',
        default=10.0,
        help='Chiết khấu dòng bán vượt ngưỡng này cần duyệt cấp Quản lý.',
    )
    discount_approval_l2_threshold = fields.Float(
        string='Ngưỡng chiết khấu L2 (%)',
        default=20.0,
        help='Chiết khấu dòng bán vượt ngưỡng này cần duyệt cấp Giám đốc.',
    )
