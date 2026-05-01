# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Schema Rx đồng bộ với pos.order.line (vnop_pos_optical):
    # khi đại lý đặt hàng cắt theo đơn (RX), bán buôn nhập tay Rx ở SO line.
    rx_od_sph = fields.Float(string='OD - SPH', digits=(4, 2))
    rx_od_cyl = fields.Float(string='OD - CYL', digits=(4, 2))
    rx_od_axis = fields.Integer(string='OD - AXIS')
    rx_od_add = fields.Float(string='OD - ADD', digits=(3, 2))

    rx_os_sph = fields.Float(string='OS - SPH', digits=(4, 2))
    rx_os_cyl = fields.Float(string='OS - CYL', digits=(4, 2))
    rx_os_axis = fields.Integer(string='OS - AXIS')
    rx_os_add = fields.Float(string='OS - ADD', digits=(3, 2))

    rx_pd = fields.Float(string='PD (mm)', digits=(4, 1))
    rx_note = fields.Char(string='Ghi chú đơn kính')
    rx_has_data = fields.Boolean(
        string='Có Rx',
        compute='_compute_rx_has_data',
        store=True,
    )

    @api.depends(
        'rx_od_sph', 'rx_od_cyl', 'rx_od_axis', 'rx_od_add',
        'rx_os_sph', 'rx_os_cyl', 'rx_os_axis', 'rx_os_add',
        'rx_pd', 'rx_note',
    )
    def _compute_rx_has_data(self):
        for line in self:
            line.rx_has_data = any((
                line.rx_od_sph, line.rx_od_cyl, line.rx_od_axis, line.rx_od_add,
                line.rx_os_sph, line.rx_os_cyl, line.rx_os_axis, line.rx_os_add,
                line.rx_pd, line.rx_note,
            ))
