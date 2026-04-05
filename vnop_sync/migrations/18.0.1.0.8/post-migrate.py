# -*- coding: utf-8 -*-
"""Bỏ seed sẵn SPH/CYL — dọn các bản ghi auto-seed không được tham chiếu.

Trước đây (18.0.1.0.6 / 18.0.1.0.7) master data SPH/CYL được seed sẵn qua
hook và migration. Từ 18.0.1.0.8, SPH/CYL chỉ được tạo on-demand khi sync
sản phẩm từ API (`_goc_power`).

Migration này xoá các bản ghi `product.lens.power` có `power_type` in
('sph', 'cyl') mà KHÔNG được bất kỳ `product.template.lens_sph_id` /
`lens_cyl_id` tham chiếu. Các bản ghi đang được dùng sẽ được giữ nguyên.

Không đụng tới các bản ghi legacy (`power_type = False`) — chúng có thể
đang phục vụ `lens_add_id` hoặc dữ liệu cũ.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    Power = env['product.lens.power']
    candidates = Power.search([('power_type', 'in', ('sph', 'cyl'))])
    if not candidates:
        return

    Template = env['product.template']
    used_sph_ids = set(
        Template.search([('lens_sph_id', 'in', candidates.ids)]).mapped('lens_sph_id').ids
    )
    used_cyl_ids = set(
        Template.search([('lens_cyl_id', 'in', candidates.ids)]).mapped('lens_cyl_id').ids
    )
    used_ids = used_sph_ids | used_cyl_ids

    to_delete = candidates.filtered(lambda r: r.id not in used_ids)
    if to_delete:
        _logger.info(
            "vnop_sync: xoá %s bản ghi product.lens.power auto-seed (SPH/CYL) không còn tham chiếu",
            len(to_delete),
        )
        to_delete.unlink()
