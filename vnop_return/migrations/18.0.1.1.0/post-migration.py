# -*- coding: utf-8 -*-
# Map code cũ (production/shipping/commercial) sang id nhóm lỗi mới rồi bỏ cột legacy.
# Chỉ join theo code khi legacy còn là varchar; idempotent với lần chạy lặp.
TABLES = ('vnop_return_reason', 'vnop_return_request_line')
_CHAR_TYPES = ('character varying', 'character', 'char', 'text')


def migrate(cr, version):
    if not version:
        return
    for table in TABLES:
        cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'defect_group_legacy'
        """, (table,))
        row = cr.fetchone()
        if not row:
            continue
        if row[0] in _CHAR_TYPES:
            cr.execute("""
                UPDATE {t} t
                   SET defect_group = g.id
                  FROM vnop_return_defect_group g
                 WHERE g.code = t.defect_group_legacy
                   AND t.defect_group IS NULL
            """.format(t=table))
        cr.execute('ALTER TABLE %s DROP COLUMN IF EXISTS defect_group_legacy' % table)

    # defect_group đổi Selection -> Many2one: dọn các bản ghi selection cũ +
    # ir.model.data của chúng. Nếu để _process_end tự unlink, core đọc
    # field.ondelete (giờ là str 'restrict' của M2o, không phải dict) -> crash.
    cr.execute(
        "DELETE FROM ir_model_data "
        "WHERE model = 'ir.model.fields.selection' AND name LIKE %s",
        ('selection__vnop_return_%defect_group__%',))
    cr.execute("""
        DELETE FROM ir_model_fields_selection s
         USING ir_model_fields f
         WHERE s.field_id = f.id
           AND f.name = 'defect_group'
           AND f.model IN ('vnop.return.reason', 'vnop.return.request.line')
    """)
