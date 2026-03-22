# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Đợt giao',
        ondelete='set null',
        index=True,
    )
    delivery_otk_id = fields.Many2one(
        'delivery.otk',
        string='Lần OTK',
        index=True,
        copy=False,
    )
    contract_ids = fields.Many2many(
        "contract",
        compute="_compute_contract_ids",
        string="Hợp đồng",
    )
    otk_session_count = fields.Integer(
        compute="_compute_otk_session_count",
        string="Số lần OTK",
    )

    def _compute_contract_ids(self):
        for picking in self:
            contracts = picking.contract_id | picking.move_ids_without_package.mapped("contract_id")
            picking.contract_ids = [(6, 0, contracts.ids)]

    def _compute_otk_session_count(self):
        grouped_by_schedule = self.env["delivery.otk"].read_group(
            [("delivery_schedule_id", "in", self.mapped("delivery_schedule_id").ids)],
            ["delivery_schedule_id"],
            ["delivery_schedule_id"],
            lazy=False,
        )
        schedule_count_map = {
            row["delivery_schedule_id"][0]: row.get("delivery_schedule_id_count", row.get("__count", 0))
            for row in grouped_by_schedule
            if row.get("delivery_schedule_id")
        }
        for picking in self:
            if picking.delivery_schedule_id:
                picking.otk_session_count = schedule_count_map.get(picking.delivery_schedule_id.id, 0)
            else:
                picking.otk_session_count = 1 if picking.delivery_otk_id else 0

    def button_validate(self):
        res = super().button_validate()
        self.mapped("delivery_otk_id")._update_done_state()
        done_pickings = self.filtered(lambda p: p.state == 'done' and p.delivery_schedule_id)
        for picking in done_pickings:
            missing_moves = picking.move_ids_without_package.filtered(lambda m: not m.delivery_schedule_id)
            missing_moves.write({'delivery_schedule_id': picking.delivery_schedule_id.id})
            picking.delivery_schedule_id._sync_state_from_receipts()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        self.mapped("delivery_otk_id")._update_done_state()
        for schedule in self.mapped('delivery_schedule_id'):
            schedule._sync_state_from_receipts()
        return res

    def action_view_otk_sessions(self):
        self.ensure_one()
        domain = [("id", "=", self.delivery_otk_id.id)] if self.delivery_otk_id else []
        if self.delivery_schedule_id:
            domain = [("delivery_schedule_id", "=", self.delivery_schedule_id.id)]
        return {
            "type": "ir.actions.act_window",
            "name": _("Lần OTK"),
            "res_model": "delivery.otk",
            "view_mode": "list,form",
            "domain": domain,
            "target": "current",
        }

    def action_create_otk_sessions(self):
        self.ensure_one()
        if self.picking_type_code != "incoming":
            raise UserError(_("Chỉ tạo OTK cho phiếu nhập kho."))
        if self.state != "done":
            raise UserError(_("Chỉ tạo OTK khi phiếu nhập kho ở trạng thái Hoàn tất."))
        if not self.delivery_schedule_id:
            raise UserError(_("Phiếu nhập kho chưa liên kết lịch giao để tạo OTK."))
        return self.delivery_schedule_id.action_create_otk_sessions()


class StockMove(models.Model):
    _inherit = "stock.move"

    delivery_otk_line_id = fields.Many2one("delivery.otk.line", string="Dòng OTK", index=True, copy=False)
