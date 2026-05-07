# -*- coding: utf-8 -*-
"""Post-migration: map giá trị Selection cũ sang record dealer.tier.

Map:
  'vip' → dealer_tier_vip
  'a'   → dealer_tier_a
  'b'   → dealer_tier_b
  'c'   → dealer_tier_c
  empty / NULL → NULL (không set)
"""


TIER_XML_IDS = {
    'vip': 'vnop_sale_channel.dealer_tier_vip',
    'a': 'vnop_sale_channel.dealer_tier_a',
    'b': 'vnop_sale_channel.dealer_tier_b',
    'c': 'vnop_sale_channel.dealer_tier_c',
}


def migrate(cr, version):
    if not version:
        return

    # Kiểm tra cột tạm có tồn tại không
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'res_partner' AND column_name = 'dealer_tier_id_old'
    """)
    if not cr.fetchone():
        return

    for selection_value, xml_id in TIER_XML_IDS.items():
        module, name = xml_id.split('.')
        cr.execute("""
            UPDATE res_partner rp
            SET dealer_tier_id = imd.res_id
            FROM ir_model_data imd
            WHERE imd.module = %s
              AND imd.name = %s
              AND rp.dealer_tier_id_old = %s
        """, (module, name, selection_value))

    # Dọn cột tạm
    cr.execute("ALTER TABLE res_partner DROP COLUMN dealer_tier_id_old")
