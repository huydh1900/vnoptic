# -*- coding: utf-8 -*-
from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()
        # Khi phiếu return về tới Kho Tạm done → đẩy request sang qc_checking
        for picking in self:
            requests = self.env['vnop.return.request'].search([
                ('return_picking_ids', 'in', picking.id),
                ('state', '=', 'goods_in_transit'),
            ])
            for req in requests:
                if all(p.state == 'done' for p in req.return_picking_ids):
                    req.state = 'qc_checking'
                    req._activity_schedule_for_role(
                        'otk',
                        f'Kiểm hàng và xác nhận tình trạng cho phiếu {req.name}',
                    )
        return res
