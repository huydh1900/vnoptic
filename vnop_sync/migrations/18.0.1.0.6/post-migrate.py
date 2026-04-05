# -*- coding: utf-8 -*-
"""Migrate product.lens.power sang mô hình có power_type (sph/cyl).

Trước đây `product.lens.power` chỉ có field `value` và được seed chung cho cả
SPH và CYL trong hook (-25..+25 step 0.25). Từ version 18.0.1.0.6, thêm field
Selection `power_type` để phân biệt SPH / CYL phục vụ ma trận tồn kho và
filter master data.

Migration script này:
  1. Tạo seed SPH (-20..+20 step 0.25) và CYL (-6..0 step 0.25) với power_type
     tương ứng, nếu chưa có.
  2. Re-point `product.template.lens_sph_id` sang bản ghi SPH cùng value.
  3. Re-point `product.template.lens_cyl_id` sang bản ghi CYL cùng value.

Các bản ghi cũ (power_type = False) vẫn được giữ lại để không phá vỡ
`lens_add_id` và dữ liệu legacy.
"""

from odoo import SUPERUSER_ID, api

STEP = 0.25
SPH_MIN, SPH_MAX = -20.00, 20.00
CYL_MIN, CYL_MAX = -6.00, 0.00


def _seed(env, power_type, v_min, v_max):
    Power = env['product.lens.power']
    existing = {
        round(v, 2): rid
        for rid, v in Power.search([('power_type', '=', power_type)]).mapped(
            lambda r: (r.id, r.value)
        )
    }
    vals_list = []
    n_steps = round((v_max - v_min) / STEP)
    for i in range(n_steps + 1):
        v = round(v_min + i * STEP, 2)
        if v not in existing:
            vals_list.append({'value': v, 'power_type': power_type})
    if vals_list:
        Power.create(vals_list)

    # Trả về map {value(round2): id} đầy đủ sau khi seed
    return {
        round(r.value, 2): r.id
        for r in Power.search([('power_type', '=', power_type)])
    }


def _repoint(env, field_name, value_to_id):
    """Cập nhật template.<field_name> sang record có power_type đúng, cùng value."""
    Template = env['product.template']
    templates = Template.search([(field_name, '!=', False)])
    if not templates:
        return 0

    updated = 0
    # Đọc value của record hiện tại theo batch để tránh N+1
    for tmpl in templates:
        old_power = tmpl[field_name]
        if not old_power:
            continue
        target_id = value_to_id.get(round(old_power.value, 2))
        if target_id and target_id != old_power.id:
            tmpl.write({field_name: target_id})
            updated += 1
    return updated


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Drop unique(value) cũ — Odoo chưa kịp dọn khi post-migrate chạy nên
    # insert SPH/CYL cùng value sẽ bị đụng. Constraint mới value_type_uniq
    # sẽ được Odoo reflect sau khi migration kết thúc.
    cr.execute(
        "ALTER TABLE product_lens_power "
        "DROP CONSTRAINT IF EXISTS product_lens_power_value_uniq"
    )

    sph_map = _seed(env, 'sph', SPH_MIN, SPH_MAX)
    cyl_map = _seed(env, 'cyl', CYL_MIN, CYL_MAX)

    _repoint(env, 'lens_sph_id', sph_map)
    _repoint(env, 'lens_cyl_id', cyl_map)
