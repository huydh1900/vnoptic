# -*- coding: utf-8 -*-
"""Restore mapping template.lens_add_id → product.lens.add sau khi Odoo
đổi comodel của field từ `product.lens.power` sang `product.lens.add`.

Dùng snapshot (tmpl_id, add_value) từ bảng tạm `_vnop_lens_add_migrate`
được tạo ở pre-migrate. Với mỗi giá trị distinct:
  1. get-or-create bản ghi `product.lens.add` có cùng value.
  2. Update `product_template.lens_add_id` về id mới.

Sau đó dọn các bản ghi `product.lens.power` có `power_type IS NULL` và
không được template nào tham chiếu nữa (residual từ luồng cũ).
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Bảng tạm có thể không tồn tại nếu pre-migrate skip (vd DB mới)
    cr.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = '_vnop_lens_add_migrate'
        )
    """)
    if not cr.fetchone()[0]:
        _logger.info("vnop_sync: không có snapshot _vnop_lens_add_migrate, skip restore")
        _cleanup_orphan_power_rows(cr)
        return

    cr.execute("SELECT tmpl_id, add_value FROM _vnop_lens_add_migrate")
    rows = cr.fetchall()
    _logger.info("vnop_sync: restore lens_add_id cho %s template", len(rows))

    env = api.Environment(cr, SUPERUSER_ID, {})
    Add = env['product.lens.add']

    # Get-or-create cache theo value để tránh search lặp
    add_cache = {}

    def _get_or_create_add_id(value):
        v = round(float(value), 2)
        if v in add_cache:
            return add_cache[v]
        rec = Add.search([('value', '=', v)], limit=1)
        if not rec:
            rec = Add.create({'value': v})
        add_cache[v] = rec.id
        return rec.id

    for tmpl_id, add_value in rows:
        if add_value is None:
            continue
        new_id = _get_or_create_add_id(add_value)
        cr.execute(
            "UPDATE product_template SET lens_add_id = %s WHERE id = %s",
            (new_id, tmpl_id),
        )

    # Dọn bảng tạm
    cr.execute("DROP TABLE IF EXISTS _vnop_lens_add_migrate")

    # Cleanup các record cũ trong product.lens.power với power_type=NULL
    # (trước đây phục vụ ADD, nay không còn ai tham chiếu).
    _cleanup_orphan_power_rows(cr)


def _cleanup_orphan_power_rows(cr):
    """Xoá các bản ghi product.lens.power có power_type IS NULL không còn
    được tham chiếu qua bất kỳ field nào:
      - product_template.lens_sph_id / lens_cyl_id
      - product_lens.sph_id / cyl_id (legacy lens detail)
    `lens_add_id` giờ đã trỏ sang product.lens.add nên không tính.
    """
    cr.execute("""
        DELETE FROM product_lens_power
        WHERE power_type IS NULL
          AND id NOT IN (
              SELECT lens_sph_id FROM product_template WHERE lens_sph_id IS NOT NULL
              UNION
              SELECT lens_cyl_id FROM product_template WHERE lens_cyl_id IS NOT NULL
              UNION
              SELECT sph_id FROM product_lens WHERE sph_id IS NOT NULL
              UNION
              SELECT cyl_id FROM product_lens WHERE cyl_id IS NOT NULL
          )
    """)
    _logger.info(
        "vnop_sync: xoá %s bản ghi product.lens.power legacy (power_type IS NULL, không tham chiếu)",
        cr.rowcount,
    )
