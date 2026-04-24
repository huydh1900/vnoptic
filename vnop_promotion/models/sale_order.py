# -*- coding: utf-8 -*-

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_trigger_domain(self):
        """Chỉ lọc các loyalty program có channel_type khớp với kênh của đơn.

        - channel_type = 'all': áp dụng cho mọi đơn
        - channel_type = 'wholesale'/'retail': chỉ áp dụng khi đơn cùng kênh
        """
        domain = super()._get_trigger_domain()
        order_channel = self.channel_type or 'retail'
        return domain + [
            ('program_id.channel_type', 'in', ('all', order_channel)),
        ]

    def _get_reward_values_discount(self, reward, coupon, **kwargs):
        """Thay prefix 'Discount' và 'On products with the following taxes' mặc định
        của sale_loyalty thành tiếng Việt để sale order line hiển thị đồng nhất."""
        values = super()._get_reward_values_discount(reward, coupon, **kwargs)
        for vals in values:
            name = vals.get('name') or ''
            if name.startswith('Discount '):
                name = 'Chiết khấu ' + name[len('Discount '):]
            name = name.replace(
                ' - On products with the following taxes: ',
                ' - Áp dụng trên sản phẩm có thuế: ',
            )
            vals['name'] = name
        return values
