# -*- coding: utf-8 -*-

from odoo import api, models


class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'

    @api.depends('reward_type', 'reward_product_id', 'discount_mode', 'reward_product_tag_id',
                 'discount', 'currency_id', 'discount_applicability', 'all_discount_product_ids')
    def _compute_description(self):
        for reward in self:
            reward_string = ""
            if reward.program_type == 'gift_card':
                reward_string = "Thẻ quà tặng"
            elif reward.program_type == 'ewallet':
                reward_string = "Ví điện tử"
            elif reward.reward_type == 'product':
                products = reward.reward_product_ids
                if len(products) == 0:
                    reward_string = "Tặng sản phẩm"
                elif len(products) == 1:
                    reward_string = "Tặng sản phẩm - %s" % reward.reward_product_id.with_context(
                        display_default_code=False
                    ).display_name
                else:
                    reward_string = "Tặng sản phẩm - [%s]" % ', '.join(
                        products.with_context(display_default_code=False).mapped('display_name')
                    )
            elif reward.reward_type == 'discount':
                format_string = '%(amount)g %(symbol)s'
                if reward.currency_id.position == 'before':
                    format_string = '%(symbol)s %(amount)g'
                formatted_amount = format_string % {
                    'amount': reward.discount,
                    'symbol': reward.currency_id.symbol,
                }
                if reward.discount_mode == 'percent':
                    reward_string = "giảm %g%% trên " % reward.discount
                elif reward.discount_mode == 'per_point':
                    reward_string = "%s mỗi điểm trên " % formatted_amount
                elif reward.discount_mode == 'per_order':
                    reward_string = "giảm %s trên " % formatted_amount
                if reward.discount_applicability == 'order':
                    reward_string += "tổng đơn hàng"
                elif reward.discount_applicability == 'cheapest':
                    reward_string += "sản phẩm rẻ nhất"
                elif reward.discount_applicability == 'specific':
                    product_available = self.env['product.product'].search(
                        reward._get_discount_product_domain(), limit=2,
                    )
                    if len(product_available) == 1:
                        reward_string += product_available.with_context(
                            display_default_code=False,
                        ).display_name
                    else:
                        reward_string += "sản phẩm chỉ định"
                if reward.discount_max_amount:
                    format_string = '%(amount)g %(symbol)s'
                    if reward.currency_id.position == 'before':
                        format_string = '%(symbol)s %(amount)g'
                    formatted_amount = format_string % {
                        'amount': reward.discount_max_amount,
                        'symbol': reward.currency_id.symbol,
                    }
                    reward_string += " (Tối đa %s)" % formatted_amount
            reward.description = reward_string
