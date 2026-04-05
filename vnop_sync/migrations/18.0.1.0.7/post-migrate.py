# -*- coding: utf-8 -*-
"""Đảm bảo master data SPH/CYL của product.lens.power luôn đầy đủ sau upgrade.

Gọi lại method idempotent `_seed_sph_cyl_master` để bổ sung các bản ghi thiếu
(trường hợp data bị xóa bằng tay hoặc môi trường chưa chạy migration 18.0.1.0.6).
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['product.lens.power']._seed_sph_cyl_master()
