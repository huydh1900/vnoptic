# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_supplier_fax = fields.Char(string='Fax')
    x_supplier_contact_name = fields.Char(string='Supplier Contact')


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    x_bank_address = fields.Char(string='Bank Address', related='bank_id.street', readonly=False, store=True)
    x_bank_branch = fields.Char(string='Bank Branch', related='bank_id.street2', readonly=False, store=True)
