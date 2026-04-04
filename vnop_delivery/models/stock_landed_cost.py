# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    delivery_schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Lịch giao',
        copy=False,
        index=True,
    )
    otk_log_id = fields.Many2one(
        'stock.otk.log',
        string='Lần OTK',
        copy=False,
        index=True,
    )
    is_provisional = fields.Boolean(string='Tạm tính', default=False, copy=False)
    is_final_adjustment = fields.Boolean(string='Điều chỉnh chốt', default=False, copy=False)
    otk_target_move_ids = fields.Many2many(
        'stock.move',
        'stock_landed_cost_otk_move_rel',
        'landed_cost_id',
        'move_id',
        string='Dòng hàng áp chi phí',
        copy=False,
    )

    def _get_targeted_move_ids(self):
        self.ensure_one()
        if self.otk_target_move_ids:
            return self.otk_target_move_ids
        return super()._get_targeted_move_ids()


class StockLandedCostLine(models.Model):
    _inherit = 'stock.landed.cost.lines'

    cost_key = fields.Char(string='Mã chi phí', copy=False, index=True)
