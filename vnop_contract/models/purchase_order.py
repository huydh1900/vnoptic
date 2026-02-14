# -*- coding: utf-8 -*-
from odoo import fields, models, api


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    contract_ids = fields.Many2many(
        "contract",
        "contract_purchase_order_rel",
        "purchase_order_id",
        "contract_id",
        string="Thuộc hợp đồng",
        copy=False,
    )

    def _get_preferred_contract(self):
        self.ensure_one()
        if len(self.contract_ids) == 1:
            return self.contract_ids
        return self.contract_ids[:1]

    def _sync_contract_to_pickings(self):
        for order in self:
            preferred_contract = order._get_preferred_contract()
            pending_pickings = order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            pending_pickings.write({"contract_id": preferred_contract.id or False})
            pending_pickings.move_ids_without_package.write({"contract_id": preferred_contract.id or False})

    def button_confirm(self):
        res = super().button_confirm()
        self._sync_contract_to_pickings()
        return res

    def write(self, vals):
        res = super().write(vals)
        if "contract_ids" in vals:
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


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    qty_remaining = fields.Float(
        string="Số lượng còn lại",
        compute="_compute_qty_remaining",
        store=True,
        digits="Product Unit of Measure",
    )

    @api.depends("product_qty", "qty_received")
    def _compute_qty_remaining(self):
        for line in self:
            line.qty_remaining = max(line.product_qty - line.qty_received, 0.0)
