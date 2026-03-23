# -*- coding: utf-8 -*-

from odoo import fields, models


class ResBank(models.Model):
    _inherit = 'res.bank'

    bank_branch_name = fields.Char(string='Chi nhánh ngân hàng')


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    bank_branch_name = fields.Char(
        string='Chi nhánh ngân hàng',
        related='bank_id.bank_branch_name',
        readonly=True,
    )
    bank_street = fields.Char(
        string='Địa chỉ ngân hàng',
        related='bank_id.street',
        readonly=True,
    )
    bank_street2 = fields.Char(
        string='Địa chỉ ngân hàng 2',
        related='bank_id.street2',
        readonly=True,
    )
    bank_city = fields.Char(
        string='Thành phố ngân hàng',
        related='bank_id.city',
        readonly=True,
    )
    bank_state_id = fields.Many2one(
        'res.country.state',
        string='Bang/Tỉnh ngân hàng',
        related='bank_id.state',
        readonly=True,
    )
    bank_country_id = fields.Many2one(
        'res.country',
        string='Quốc gia ngân hàng',
        related='bank_id.country',
        readonly=True,
    )
