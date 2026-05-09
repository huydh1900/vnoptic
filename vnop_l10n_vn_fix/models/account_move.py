from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _compute_currency_id(self):
        super()._compute_currency_id()
        vnd = self.env.ref('base.VND', raise_if_not_found=False)
        if not vnd:
            return
        for move in self:
            if move.move_type == 'out_invoice':
                move.currency_id = vnd
