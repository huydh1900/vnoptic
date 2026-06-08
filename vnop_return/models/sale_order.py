# -*- coding: utf-8 -*-
from odoo import _, models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    return_request_count = fields.Integer(
        string='Số phiếu trả hàng lỗi',
        compute='_compute_return_request_count')

    def _compute_return_request_count(self):
        # sudo + read_group: đếm không phụ thuộc quyền module trả hàng nên không
        # chặn user mở đơn; không N+1.
        groups = self.env['vnop.return.request'].sudo()._read_group(
            [('sale_order_id', 'in', self.ids)],
            groupby=['sale_order_id'], aggregates=['__count'])
        counts = {order.id: count for order, count in groups}
        for order in self:
            order.return_request_count = counts.get(order.id, 0)

    def action_view_return_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Phiếu trả hàng lỗi'),
            'res_model': 'vnop.return.request',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_sale_order_id': self.id,
                'default_partner_id': self.partner_id.id,
            },
        }
