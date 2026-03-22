# -*- coding: utf-8 -*-
"""
Migration 18.0.1.0.2 – Chuẩn hóa lens fields
- Drop x_design_1, x_design_2 columns (đã thay bằng lens_design1_id / lens_design2_id Many2one)
- Add x_material_id, x_refractive_index_id, x_coating_id (Odoo tự tạo qua ORM)
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("🔄 Migration 18.0.1.0.2: chuẩn hóa lens fields bắt đầu...")

    # Xóa cột x_design_1 nếu còn tồn tại
    for col in ('x_design_1', 'x_design_2'):
        cr.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'product_template' AND column_name = '{col}'
        """)
        if cr.fetchone():
            cr.execute(f"ALTER TABLE product_template DROP COLUMN IF EXISTS {col}")
            _logger.info(f"✅ Đã drop column product_template.{col}")
        else:
            _logger.info(f"ℹ️  Column product_template.{col} không tồn tại, bỏ qua.")

    _logger.info("✅ Migration 18.0.1.0.2 hoàn tất.")
