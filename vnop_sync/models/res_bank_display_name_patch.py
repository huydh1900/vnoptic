from odoo import models, api

class ResBank(models.Model):
    _inherit = 'res.bank'

    @api.depends('name', 'country')
    def _compute_display_name(self):
        for bank in self:
            name = bank.name or ''
            country = bank.country.name if bank.country else ''
            if country:
                bank.display_name = f"{name} - {country}"
            else:
                bank.display_name = name
