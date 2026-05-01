# -*- coding: utf-8 -*-

from odoo import api, fields, models


# Common Rx schema dùng chung cho pos.order.line và sale.order.line.
# Khi cần thêm/đổi field Rx → đồng bộ ở vnop_sale_channel.models.sale_order.
RX_FIELD_NAMES = (
    'rx_od_sph', 'rx_od_cyl', 'rx_od_axis', 'rx_od_add',
    'rx_os_sph', 'rx_os_cyl', 'rx_os_axis', 'rx_os_add',
    'rx_pd', 'rx_note', 'rx_has_data',
)


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    # OD = Oculus Dexter (mắt phải), OS = Oculus Sinister (mắt trái).
    # Dải hợp lý: SPH ±20 / CYL ±10 / AXIS 0-180 / ADD 0-4 / PD 40-80.
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

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        for fname in RX_FIELD_NAMES:
            if fname not in fields_list:
                fields_list.append(fname)
        return fields_list
