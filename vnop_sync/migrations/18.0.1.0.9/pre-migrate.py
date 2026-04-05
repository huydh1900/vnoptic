# -*- coding: utf-8 -*-
"""Snapshot mapping product_template.lens_add_id → value, rồi NULL cột
trước khi Odoo đổi FK của field sang model mới `product.lens.add`.

Lý do: `product_template.lens_add_id` trước đây trỏ `product_lens_power.id`
(các record có `power_type IS NULL`). Sau upgrade, field trỏ tới
`product_lens_add.id` — các giá trị int cũ không còn hợp lệ và sẽ vi phạm
foreign key constraint mới. Pre-migrate này lưu lại mapping (tmpl_id, value)
vào bảng tạm `_vnop_lens_add_migrate`; post-migrate sẽ restore bằng id mới.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Tạo bảng tạm (giữ trong cùng transaction, persistent cho tới post-migrate)
    cr.execute("""
        CREATE TABLE IF NOT EXISTS _vnop_lens_add_migrate (
            tmpl_id   INTEGER PRIMARY KEY,
            add_value NUMERIC(8, 2)
        )
    """)
    cr.execute("TRUNCATE _vnop_lens_add_migrate")

    cr.execute("""
        INSERT INTO _vnop_lens_add_migrate (tmpl_id, add_value)
        SELECT pt.id, plp.value
        FROM product_template pt
        JOIN product_lens_power plp ON pt.lens_add_id = plp.id
        WHERE pt.lens_add_id IS NOT NULL
    """)
    snapshot_count = cr.rowcount
    _logger.info(
        "vnop_sync: snapshot %s template → lens_add_id trước khi đổi comodel",
        snapshot_count,
    )

    # NULL cột lens_add_id để schema change không bị FK constraint chặn
    cr.execute(
        "UPDATE product_template SET lens_add_id = NULL WHERE lens_add_id IS NOT NULL"
    )
