# -*- coding: utf-8 -*-

from odoo import api, fields, models


class VnopWard(models.Model):
    _name = 'vnop.ward'
    _description = 'Phường/Xã Việt Nam (sau sáp nhập 2025-07-01)'
    _order = 'state_id, name'
    _rec_name = 'name'

    name = fields.Char(string='Tên Phường/Xã', required=True, index=True)
    code = fields.Char(string='Mã GSO', index=True)
    state_id = fields.Many2one(
        'res.country.state', string='Tỉnh/Thành phố',
        required=True, ondelete='cascade', index=True,
    )
    country_id = fields.Many2one(
        'res.country', related='state_id.country_id', store=True, readonly=True,
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Mã phường/xã đã tồn tại.'),
    ]

    @api.depends('name', 'state_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.name or ''
