# -*- coding: utf-8 -*-
"""Pre-migration: chuyển dealer_tier_id từ Selection (varchar) sang M2o (int4).

Chiến lược:
1. Sao lưu giá trị Selection cũ vào cột tạm dealer_tier_id_old.
2. Drop cột dealer_tier_id gốc để Odoo tạo lại kiểu int4 (M2o).
Post-migrate sẽ map giá trị cũ sang record dealer.tier tương ứng.
"""


def migrate(cr, version):
    if not version:
        return

    # Cleanup các bản ghi ir.model.fields.selection cũ của field Selection trước đây.
    # Phải chạy idempotent (kể cả khi cột đã được migrate ở lần chạy trước) vì
    # nếu để lại, _process_end của ir.model.data sẽ unlink chúng và gọi
    # _process_ondelete với field giờ là Many2one (ondelete là str 'restrict'),
    # gây AttributeError: 'str' object has no attribute 'get'.
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.model.fields.selection'
          AND res_id IN (
              SELECT s.id
              FROM ir_model_fields_selection s
              JOIN ir_model_fields f ON f.id = s.field_id
              WHERE f.model = 'res.partner' AND f.name = 'dealer_tier_id'
          )
    """)
    cr.execute("""
        DELETE FROM ir_model_fields_selection
        WHERE field_id IN (
            SELECT id FROM ir_model_fields
            WHERE model = 'res.partner' AND name = 'dealer_tier_id'
        )
    """)

    # Kiểm tra cột dealer_tier_id có tồn tại không (tránh lỗi nếu chạy lại)
    cr.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'res_partner' AND column_name = 'dealer_tier_id'
    """)
    row = cr.fetchone()
    if not row:
        return

    # Nếu đã là int4 (đã migrate rồi), bỏ qua phần chuyển kiểu cột
    if row[1] in ('integer', 'int4', 'bigint'):
        return

    # Tạo cột tạm để lưu giá trị Selection cũ (varchar)
    cr.execute("""
        ALTER TABLE res_partner
        ADD COLUMN IF NOT EXISTS dealer_tier_id_old VARCHAR
    """)
    cr.execute("""
        UPDATE res_partner
        SET dealer_tier_id_old = dealer_tier_id::text
        WHERE dealer_tier_id IS NOT NULL AND dealer_tier_id != ''
    """)

    # Drop cột cũ để Odoo tạo lại kiểu int4 (M2o ref)
    cr.execute("ALTER TABLE res_partner DROP COLUMN dealer_tier_id")
