from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends('pricelist_id', 'company_id')
    def _compute_currency_id(self):
        vnd = self.env.ref('base.VND', raise_if_not_found=False)
        if not vnd:
            return super()._compute_currency_id()
        for order in self:
            order.currency_id = vnd
