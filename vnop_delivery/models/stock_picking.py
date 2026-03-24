# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Đợt giao',
        ondelete='set null',
        index=True,
    )
    is_temp_location = fields.Boolean(compute='_compute_is_temp_location', store=True)
    otk_id = fields.Many2one('stock.otk', string='OTK', index=True)
    otk_ok_id = fields.Many2one('stock.otk', string='OTK (hàng đạt)', index=True)
    otk_ng_id = fields.Many2one('stock.otk', string='OTK (hàng lỗi)', index=True)
    otk_count = fields.Integer(compute='_compute_otk_count')

    @api.depends('location_dest_id')
    def _compute_is_temp_location(self):
        temp = self.env.ref('vnop_delivery.location_temp_incoming', raise_if_not_found=False)
        for rec in self:
            rec.is_temp_location = temp and rec.location_dest_id.id == temp.id

    def _compute_otk_count(self):
        data = self.env['stock.otk'].read_group(
            [('picking_id', 'in', self.ids)], ['picking_id'], ['picking_id']
        )
        counts = {d['picking_id'][0]: d['picking_id_count'] for d in data}
        for rec in self:
            rec.otk_count = counts.get(rec.id, 0)

    def action_view_otk(self):
        otk = self.env['stock.otk'].search([('picking_id', '=', self.id)])
        action = {
            'type': 'ir.actions.act_window',
            'name': 'OTK',
            'res_model': 'stock.otk',
            'context': {'default_picking_id': self.id},
        }
        if len(otk) == 1:
            action.update({'view_mode': 'form', 'res_id': otk.id})
        else:
            action.update({'view_mode': 'list,form', 'domain': [('picking_id', '=', self.id)]})
        return action

    def action_create_otk(self):
        self.ensure_one()
        otk = self.env['stock.otk'].search([('picking_id', '=', self.id)], limit=1)
        if not otk:
            lines = [(0, 0, {
                'product_id': move.product_id.id,
                'uom_id': move.product_uom.id,
                'move_id': move.id,
                'qty_received': move.quantity,
            }) for move in self.move_ids]
            otk = self.env['stock.otk'].create({
                'picking_id': self.id,
                'partner_id': self.partner_id.id,
                'line_ids': lines,
            })
            self.otk_id = otk

        check = self.env['stock.otk.check'].create({
            'otk_id': otk.id,
            'line_ids': [(0, 0, {
                'product_id': l.product_id.id,
                'uom_id': l.uom_id.id,
                'otk_line_id': l.id,
                'qty_to_check': l.qty_remaining,
            }) for l in otk.line_ids if l.qty_remaining > 0],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.otk.check',
            'view_mode': 'form',
            'res_id': check.id,
            'target': 'current',
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
