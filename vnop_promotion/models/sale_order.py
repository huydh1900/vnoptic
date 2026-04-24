# -*- coding: utf-8 -*-

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_program_domain(self):
        """Filter loyalty.program theo kênh bán của đơn (áp cho program auto)."""
        domain = super()._get_program_domain()
        order_channel = self.channel_type or 'retail'
        return domain + [('channel_type', 'in', ('all', order_channel))]

    def _get_trigger_domain(self):
        """Filter loyalty.rule theo kênh bán của đơn (áp cho program with_code)."""
        domain = super()._get_trigger_domain()
        order_channel = self.channel_type or 'retail'
        return domain + [
            ('program_id.channel_type', 'in', ('all', order_channel)),
        ]

    def action_open_reward_wizard(self):
        """Luôn mở wizard chọn chiết khấu thay vì auto-apply khi chỉ có 1 reward."""
        self.ensure_one()
        self._update_programs_and_rewards()
        if not self._get_claimable_rewards():
            return True
        return self.env['ir.actions.actions']._for_xml_id(
            'sale_loyalty.sale_loyalty_reward_wizard_action'
        )

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
