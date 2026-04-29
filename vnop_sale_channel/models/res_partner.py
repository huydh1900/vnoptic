# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    channel_type = fields.Selection(
        selection=[
            ('wholesale', 'Bán buôn'),
            ('retail', 'Bán lẻ'),
        ],
        string='Kênh bán',
        help='Phân loại khách hàng theo kênh bán buôn hoặc bán lẻ.',
    )

    @api.model
    def default_get(self, fields_list):
        """Đảm bảo channel_type lấy đúng từ context.

        Lý do override thay vì để field default xử lý: trong 1 số path
        (m2o quick-create, NameAndShortcuts), Odoo có thể serialize sẵn
        default trong arch view trước khi context action được merge,
        khiến static `default='retail'` lấn át `default_channel_type` của
        action menu_wholesale_*. Ép tay ở default_get bảo đảm context thắng.
        """
        res = super().default_get(fields_list)
        if 'channel_type' in fields_list:
            ctx_channel = self.env.context.get('default_channel_type')
            if ctx_channel in ('wholesale', 'retail'):
                res['channel_type'] = ctx_channel
            elif not res.get('channel_type'):
                res['channel_type'] = 'retail'
        return res
