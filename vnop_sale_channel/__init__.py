# -*- coding: utf-8 -*-

from . import models
from . import wizard


def post_init_hook(env):
    """Bật use_partner_credit_limit cho các partner đã là khách bán buôn.

    Lý do: Odoo mặc định tắt kiểm tra hạn mức ở mức partner. Với B2B (wholesale),
    luôn cần bật để cảnh báo vượt công nợ trên đơn hàng. Module mới cài → set
    cho data sẵn có; partner tạo mới sau đó user tự chọn (không can thiệp default
    để tránh ép logic ngoài scope).
    """
    wholesale_partners = env['res.partner'].search([
        ('channel_type', '=', 'wholesale'),
        ('use_partner_credit_limit', '=', False),
    ])
    if wholesale_partners:
        wholesale_partners.write({'use_partner_credit_limit': True})
