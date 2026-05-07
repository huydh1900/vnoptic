"""Backfill product_template.legacy_product_id từ x_java_qr_url.

Trước version 18.0.1.2.0, hệ thống chỉ lưu URL Java đầy đủ trong
`x_java_qr_url` (dạng https://erp.vnoptictech.com.vn/product/<java_id>).
Giờ ta tách ID ra cột riêng để controller portal có thể lookup nhanh
và để hỗ trợ chuyển domain Java -> Odoo mà không cần tem QR mới.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        UPDATE product_template
           SET legacy_product_id = CAST(
                   substring(x_java_qr_url FROM '/product/([0-9]+)/?$') AS INTEGER
               )
         WHERE x_java_qr_url ~ '/product/[0-9]+/?$'
           AND (legacy_product_id IS NULL OR legacy_product_id = 0)
        """
    )
    _logger.info(
        "vnop_sync 18.0.1.2.0: backfilled legacy_product_id cho %s sản phẩm",
        cr.rowcount,
    )
