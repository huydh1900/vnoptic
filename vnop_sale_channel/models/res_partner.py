# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dealer_tier_id = fields.Many2one(
        comodel_name='dealer.tier',
        string='Hạng đại lý',
        tracking=True,
        ondelete='restrict',
        # ondelete='restrict': không cho xóa hạng khi còn đại lý đang dùng
        help='VIP cao nhất → Tiêu chuẩn thấp nhất. Dùng cho phân loại đại lý B2B.',
    )

    # Override credit_limit (account) chỉ để bật tracking — giữ nguyên type Float
    # và các thuộc tính khác (groups, company_dependent) qua kế thừa Odoo ORM.
    credit_limit = fields.Float(tracking=True)

    credit_used_pct = fields.Float(
        string='% Hạn mức đã dùng',
        compute='_compute_credit_used_pct',
        groups='account.group_account_invoice,account.group_account_readonly',
        help='Tỉ lệ phần trăm công nợ hiện tại trên hạn mức. 100% = đã dùng hết hạn mức.',
    )

    @api.depends('credit', 'credit_limit')
    def _compute_credit_used_pct(self):
        for partner in self:
            if partner.credit_limit:
                partner.credit_used_pct = (partner.credit / partner.credit_limit) * 100.0
            else:
                partner.credit_used_pct = 0.0
