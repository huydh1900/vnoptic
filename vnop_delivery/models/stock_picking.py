# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


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


class StockMove(models.Model):
    _inherit = "stock.move"

    delivery_otk_line_id = fields.Many2one("delivery.otk.line", string="Dòng OTK", index=True, copy=False)
