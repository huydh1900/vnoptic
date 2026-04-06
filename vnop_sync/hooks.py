# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    """
    Generate initial SPH and CYL data for product.lens.power
    This runs only once after module installation.
    """
    env['res.partner.bank'].migrate_invalid_bank_fields()
    # SPH/CYL master data KHÔNG seed sẵn — sẽ được tạo on-demand khi sync
    # sản phẩm từ API (xem `_goc_power` trong product_sync.py).

    # 3. Generate Basic Designs
    Design = env['product.lens.design']
    if Design.search_count([]) == 0:
        Design.create([
            {'name': 'Single Vision', 'code': 'SV', 'design_type': 'single'},
            {'name': 'Progressive', 'code': 'PROG', 'design_type': 'progressive'},
            {'name': 'Bifocal', 'code': 'BI', 'design_type': 'bifocal'},
        ])

    # 4. Generate Materials
    Material = env['product.lens.material']
    if Material.search_count([]) == 0:
        Material.create([
            {'name': '1.50 Standard', 'refractive_index': 1.50},
            {'name': '1.56 Mid-Index', 'refractive_index': 1.56},
            {'name': '1.60 High-Index', 'refractive_index': 1.60},
            {'name': '1.67 High-Index', 'refractive_index': 1.67},
            {'name': '1.74 Ultra High-Index', 'refractive_index': 1.74},
            {'name': 'Polycarbonate', 'refractive_index': 1.59},
        ])
    
    # 5. Generate Features
    Feature = env['product.lens.feature']
    if Feature.search_count([]) == 0:
        Feature.create([
            {'name': 'UV400', 'feature_type': 'uv'},
            {'name': 'UV420 (Blue Cut)', 'feature_type': 'blue'},
            {'name': 'HMC Standard', 'feature_type': 'hmc'},
            {'name': 'Super Hydrophobic', 'feature_type': 'hmc'},
            {'name': 'Photochromic Grey', 'feature_type': 'photochromic'},
            {'name': 'Photochromic Brown', 'feature_type': 'photochromic'},
        ])

    # Keep export templates in sync with vnop import rules.
    env['product.template']._ensure_vnop_export_templates()
