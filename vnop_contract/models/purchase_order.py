# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    contract_id = fields.Many2one(
        "contract",
        string="Hợp đồng khung",
        copy=False,
        index=True,
    )
    def _sync_contract_to_pickings(self):
        for order in self.filtered("contract_id"):
            pending_pickings = order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            pending_pickings.write({"contract_id": order.contract_id.id})
            pending_pickings.move_ids_without_package.write({"contract_id": order.contract_id.id})

    def button_confirm(self):
        res = super().button_confirm()
        self._sync_contract_to_pickings()
        return res

    def write(self, vals):
        res = super().write(vals)
        if "contract_id" in vals:
            self._sync_contract_to_pickings()
        return res

    def action_view_purchase(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }
