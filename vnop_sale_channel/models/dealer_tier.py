# -*- coding: utf-8 -*-

from odoo import fields, models


class DealerTier(models.Model):
    _name = 'dealer.tier'
    _description = 'Hạng đại lý'
    _order = 'sequence, code'

    code = fields.Char(string='Mã hạng', required=True, size=10)
    name = fields.Char(string='Tên hạng', required=True, translate=True)
    sequence = fields.Integer(default=10)
    default_discount = fields.Float(
        string='Chiết khấu mặc định (%)',
        help='Áp khi tạo đơn cho khách thuộc hạng này',
    )
    suggested_credit_limit = fields.Monetary(
        string='Hạn mức gợi ý',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    active = fields.Boolean(default=True)
    description = fields.Text(string='Mô tả')
    partner_count = fields.Integer(string='Số đại lý', compute='_compute_partner_count')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Mã hạng đại lý phải là duy nhất.'),
    ]

    def _compute_partner_count(self):
        # Dùng read_group để batch count thay vì search trong loop
        domain = [('dealer_tier_id', 'in', self.ids)]
        groups = self.env['res.partner'].read_group(domain, ['dealer_tier_id'], ['dealer_tier_id'])
        count_map = {g['dealer_tier_id'][0]: g['dealer_tier_id_count'] for g in groups}
        for tier in self:
            tier.partner_count = count_map.get(tier.id, 0)
