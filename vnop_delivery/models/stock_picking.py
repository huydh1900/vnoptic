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

    # Đếm phiếu chuyển kho OK/NG được tạo từ OTK trên picking này
    # Tìm qua stock.otk.log vì log ghi nhận picking_id + transfer_ok_id/transfer_ng_id
    otk_log_ids = fields.One2many('stock.otk.log', 'picking_id', string='OTK Logs')
    otk_transfer_ok_count = fields.Integer(
        string='Chuyển kho đạt', compute='_compute_otk_transfer_count',
    )
    otk_transfer_ng_count = fields.Integer(
        string='Chuyển kho lỗi', compute='_compute_otk_transfer_count',
    )

    @api.depends('otk_log_ids.transfer_ok_id', 'otk_log_ids.transfer_ng_id')
    def _compute_otk_transfer_count(self):
        for picking in self:
            logs = picking.otk_log_ids
            picking.otk_transfer_ok_count = len(logs.transfer_ok_id)
            picking.otk_transfer_ng_count = len(logs.transfer_ng_id)

    def action_view_otk_transfer_ok(self):
        """Mở danh sách phiếu chuyển kho đạt tạo từ OTK."""
        self.ensure_one()
        transfer_ids = self.otk_log_ids.transfer_ok_id.ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Chuyển kho đạt'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', transfer_ids)],
        }

    def action_view_otk_transfer_ng(self):
        """Mở danh sách phiếu chuyển kho lỗi tạo từ OTK."""
        self.ensure_one()
        transfer_ids = self.otk_log_ids.transfer_ng_id.ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Chuyển kho lỗi'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', transfer_ids)],
        }

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
            picking.delivery_schedule_id._sync_state_from_receipts()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        for schedule in self.mapped('delivery_schedule_id'):
            schedule._sync_state_from_receipts()
        return res
