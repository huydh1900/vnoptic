# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    """
    Generate initial SPH and CYL data for product.lens.power
    This runs only once after module installation.
    """
    env['res.partner.bank'].migrate_invalid_bank_fields()
    # Use environment with superuser to ensure permissions
    # env argument in hook is actually a cursor in older versions or Environment in newer?
    # In Odoo 18 hooks usually receive cr or env. 
    # Let's assume standard signature: def post_init_hook(env) -> Odoo 17+ style
    
    # Check if data exists
    Power = env['product.lens.power']
    if Power.search_count([]) > 0:
        return

    vals_list = []
    sph_min, sph_max, step = -25.00, 25.00, 0.25
    current = sph_min
    while current <= sph_max + 0.001:
        vals_list.append({'value': current})
        current += step

    if vals_list:
        Power.create(vals_list)
        
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
