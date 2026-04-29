import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Cấu hình hậu cài đặt cho POS Mắt kính.

    1. Bật available_in_pos cho catalog gốc (gọng, tròng, phụ kiện) để
       POS không trống.
    2. Gán payment_method_ids + limit_categories cho pos.config qua hook
       (không qua XML) để tránh ParseError khi -u nếu phiên POS đang mở.
       Hook chỉ chạy lúc install, không ảnh hưởng phiên đang mở sau này.
    """
    Product = env['product.template']
    products = Product.search([
        ('active', '=', True),
        ('sale_ok', '=', True),
        ('type', 'in', ['consu', 'product']),
        ('available_in_pos', '=', False),
    ])
    if products:
        products.write({'available_in_pos': True})
    _logger.info(
        "vnop_pos_optical: enabled POS availability on %d products",
        len(products),
    )

    config = env.ref('vnop_pos_optical.pos_config_optical_main', raise_if_not_found=False)
    if config and not config.current_session_id:
        method_xmlids = [
            'vnop_pos_optical.payment_method_cash_optical',
            'vnop_pos_optical.payment_method_bank_transfer',
            'vnop_pos_optical.payment_method_card_pos',
            'vnop_pos_optical.payment_method_momo',
            'vnop_pos_optical.payment_method_vnpay',
            'vnop_pos_optical.payment_method_zalopay',
            'vnop_pos_optical.payment_method_voucher',
        ]
        method_ids = []
        for xmlid in method_xmlids:
            method = env.ref(xmlid, raise_if_not_found=False)
            if method:
                method_ids.append(method.id)
        if method_ids:
            config.write({
                'limit_categories': False,
                'payment_method_ids': [(6, 0, method_ids)],
            })
