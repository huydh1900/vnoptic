# -*- coding: utf-8 -*-
# defect_group: Selection (varchar) -> Many2one (vnop.return.defect.group).
# Chỉ rename khi cột còn là varchar (Selection cũ); nếu đã là integer
# (đã convert ở lần chạy trước) thì bỏ qua để idempotent.
TABLES = ('vnop_return_reason', 'vnop_return_request_line')
_CHAR_TYPES = ('character varying', 'character', 'char', 'text')


def migrate(cr, version):
    if not version:
        return
    for table in TABLES:
        cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'defect_group'
        """, (table,))
        row = cr.fetchone()
        if row and row[0] in _CHAR_TYPES:
            cr.execute(
                'ALTER TABLE %s RENAME COLUMN defect_group TO defect_group_legacy'
                % table)
