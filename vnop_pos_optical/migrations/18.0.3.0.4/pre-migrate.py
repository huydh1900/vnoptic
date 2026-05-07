# -*- coding: utf-8 -*-


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        UPDATE product_category
        SET vnop_pos_category_id = NULL
        WHERE vnop_pos_category_id IS NOT NULL
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'pos.category'
    """)
    cr.execute("DELETE FROM pos_category")
