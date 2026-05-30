# -*- coding: utf-8 -*-

from odoo import api, models


class ResCountryState(models.Model):
    _inherit = 'res.country.state'

    @api.depends('name')
    def _compute_display_name(self):
        for state in self:
            state.display_name = state.name or ''
