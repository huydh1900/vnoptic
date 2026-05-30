# -*- coding: utf-8 -*-
from odoo import models


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _prepare_picking_default_values_based_on(self, picking):
        """Cho phép redirect đích phiếu trả về Kho Tạm (để OTK kiểm trước khi
        nhập kho thật) thay vì kho nguồn mặc định của phiếu giao.

        Wizard chuẩn đưa hàng về `picking.location_id` (kho xuất). Flow trả hàng
        đại lý của vnop_return cần hàng về Kho Tạm để OTK phân loại, nên truyền
        location đích qua context `vnop_return_dest_location_id`. Các move con tự
        lấy theo `new_picking.location_dest_id` nên chỉ cần override ở đây.
        """
        vals = super()._prepare_picking_default_values_based_on(picking)
        dest_loc_id = self.env.context.get('vnop_return_dest_location_id')
        if dest_loc_id:
            vals['location_dest_id'] = dest_loc_id
        return vals
