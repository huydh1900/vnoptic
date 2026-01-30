# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Đợt giao',
        ondelete='set null',
        index=True,
    )

    qc_state = fields.Selection([
        ('none', 'Chưa OTK'),
        ('qc_done', 'Đã OTK'),
    ], default='none', tracking=True)

    qc_note = fields.Text(string='Ghi chú QC')

    def action_open_otk_wizard(self):
        self.ensure_one()

        if self.picking_type_id.code != 'incoming':
            raise UserError('OTK chỉ áp dụng cho phiếu nhập (Receipt).')

        if self.state != 'done':
            raise UserError('Vui lòng xác nhận phiếu nhập trước khi OTK.')

        if self.qc_state == 'done':
            raise UserError('Phiếu nhập này đã OTK rồi.')

        return {
            'type': 'ir.actions.act_window',
            'name': 'OTK Receipt',
            'res_model': 'otk.receipt.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.id,
            }
        }
