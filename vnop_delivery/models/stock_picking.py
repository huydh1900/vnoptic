# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Đợt giao',
        ondelete='set null',
        index=True,
    )
    is_temp_location = fields.Boolean(compute='_compute_is_temp_location', store=True)

    @api.depends('location_dest_id')
    def _compute_is_temp_location(self):
        temp = self.env.ref('vnop_delivery.location_temp_incoming', raise_if_not_found=False)
        for rec in self:
            rec.is_temp_location = bool(temp and rec.location_dest_id.id == temp.id)

    def action_otk(self):
        self.ensure_one()
        wizard = self.env['stock.otk.wizard'].with_context(
            default_picking_id=self.id
        ).create({'picking_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'OTK - Kiểm hàng',
            'res_model': 'stock.otk.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def button_validate(self):
        res = super().button_validate()
        done_pickings = self.filtered(lambda p: p.state == 'done' and p.delivery_schedule_id)
        for picking in done_pickings:
            missing_moves = picking.move_ids_without_package.filtered(lambda m: not m.delivery_schedule_id)
            missing_moves.write({'delivery_schedule_id': picking.delivery_schedule_id.id})
            picking.delivery_schedule_id._sync_state_from_receipts()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        for schedule in self.mapped('delivery_schedule_id'):
            schedule._sync_state_from_receipts()
        return res
