# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    """
    Generate initial SPH and CYL data for product.lens.power
    This runs only once after module installation.
    """
    # Use environment with superuser to ensure permissions
    # env argument in hook is actually a cursor in older versions or Environment in newer?
    # In Odoo 18 hooks usually receive cr or env. 
    # Let's assume standard signature: def post_init_hook(env) -> Odoo 17+ style
    
    # Check if data exists
    Power = env['product.lens.power']
    if Power.search_count([]) > 0:
        return

    vals_list = []
    
    # 1. Generate SPH: -25.00 to +25.00, step 0.25
    # Range is inclusive
    sph_min = -25.00
    sph_max = 25.00
    step = 0.25
    
    current = sph_min
    while current <= sph_max + 0.001:
        # Determine display name
        if abs(current) < 0.001:
            name = "0.00" # Plano
        else:
            name = "{:+.2f}".format(current)
            
        vals_list.append({
            'name': name,
            'value': current,
            'type': 'sph'
        })
        current += step

    # 2. Generate CYL: -12.00 to +12.00, step 0.25
    cyl_min = -12.00
    cyl_max = 12.00
    
    current = cyl_min
    while current <= cyl_max + 0.001:
        if abs(current) < 0.001:
            name = "0.00"
        else:
            name = "{:+.2f}".format(current)
            
        vals_list.append({
            'name': name,
            'value': current,
            'type': 'cyl'
        })
        current += step
        
    # Bulk create
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
