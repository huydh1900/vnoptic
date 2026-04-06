# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.osv import expression


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    contract_id = fields.Many2one(
        'contract', string='Hợp đồng', index=True, copy=False, readonly=True,
    )

    def _get_gather_domain(self, product_id, location_id, lot_id=None,
                           package_id=None, owner_id=None, strict=False):
        domain = super()._get_gather_domain(
            product_id, location_id, lot_id, package_id, owner_id, strict,
        )
        contract_id = self.env.context.get('quant_contract_id')
        if contract_id is not None:
            domain = expression.AND([
                [('contract_id', '=', contract_id or False)], domain,
            ])
        return domain

    def _gather(self, product_id, location_id, lot_id=None, package_id=None,
                owner_id=None, strict=False, qty=0):
        res = super()._gather(
            product_id, location_id, lot_id, package_id, owner_id, strict, qty,
        )
        # Cache path in super() bypasses _get_gather_domain, so filter here
        contract_id = self.env.context.get('quant_contract_id')
        if contract_id is not None and res:
            res = res.filtered(
                lambda q: q.contract_id.id == (contract_id or False)
            )
        return res

    @api.model_create_multi
    def create(self, vals_list):
        contract_id = self.env.context.get('quant_contract_id')
        if contract_id is not None:
            for vals in vals_list:
                vals.setdefault('contract_id', contract_id or False)
        return super().create(vals_list)