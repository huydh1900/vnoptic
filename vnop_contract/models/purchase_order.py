# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    contract_id = fields.Many2one(
        "contract",
        string="Hợp đồng",
        compute="_compute_contract_id",
        inverse="_inverse_contract_id",
        store=True,
        copy=False,
    )

    contract_ids = fields.Many2many(
        "contract",
        "contract_purchase_order_rel",
        "purchase_order_id",
        "contract_id",
        string="Thuộc hợp đồng",
        copy=False,
    )

    @api.depends("contract_ids")
    def _compute_contract_id(self):
        for order in self:
            order.contract_id = order.contract_ids[:1].id or False

    def _inverse_contract_id(self):
        for order in self:
            if order.contract_id:
                order.contract_ids = [(6, 0, [order.contract_id.id])]
            else:
                order.contract_ids = [(5, 0, 0)]

    @api.constrains("contract_ids")
    def _check_single_contract(self):
        for order in self:
            if len(order.contract_ids) > 1:
                raise ValidationError(_("Mỗi đơn mua chỉ được liên kết một hợp đồng."))

    def _get_preferred_contract(self):
        self.ensure_one()
        return self.contract_id

    def _sync_contract_to_pickings(self):
        for order in self:
            preferred_contract = order._get_preferred_contract()
            pending_pickings = order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            pending_pickings.write({"contract_id": preferred_contract.id if preferred_contract else False})
            pending_pickings.move_ids_without_package.write({"contract_id": preferred_contract.id if preferred_contract else False})

    def button_confirm(self):
        res = super().button_confirm()
        self._sync_contract_to_pickings()
        return res

    def write(self, vals):
        res = super().write(vals)
        if "contract_ids" in vals or "contract_id" in vals:
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

    contract_line_ids = fields.One2many(
        "contract.line",
        "purchase_line_id",
        string="Dòng hợp đồng",
        readonly=True,
    )
    contract_line_id = fields.Many2one(
        "contract.line",
        string="Dòng hợp đồng",
        compute="_compute_contract_line_id",
        readonly=True,
    )
    qty_remaining = fields.Float(
        string="Số lượng còn lại",
        compute="_compute_qty_remaining",
        store=True,
        digits="Product Unit of Measure",
    )

    @api.depends("contract_line_ids")
    def _compute_contract_line_id(self):
        for line in self:
            line.contract_line_id = line.contract_line_ids[:1].id or False

    @api.depends("product_qty", "qty_received")
    def _compute_qty_remaining(self):
        for line in self:
            line.qty_remaining = max(line.product_qty - line.qty_received, 0.0)
