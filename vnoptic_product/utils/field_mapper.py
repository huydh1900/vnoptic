# -*- coding: utf-8 -*-
"""
Field mapping from Excel headers to Odoo model fields
Maps English headers (Row 10 in Excel) to Odoo field names
"""

# Common fields for all product types
COMMON_FIELD_MAP = {
    'Group': 'group_id',
    'Image': 'image_1920',
    'FullName': 'name',
    'EngName': 'eng_name',
    'TradeName': 'trade_name',
    'Unit': 'unit',
    'TradeMark': 'brand_id',
    'Supplier': 'supplier_id',
    'Country': 'country_id',
    'Supplier_Warranty': 'supplier_warranty_id',
    'Warranty': 'warranty_id',
    'Warranty_Retail': 'warranty_retail_id',
    'Accessory': 'accessory_ids',
    'Origin_Price': 'x_or_price',
    'Currency': 'currency_zone_id',
    'Cost_Price': 'x_ct_price',
    'Retail_Price': 'list_price',
    'Wholesale_Price': 'x_ws_price',
    'Wholesale_Price_Max': 'x_ws_price_max',
    'Wholesale_Price_Min': 'x_ws_price_min',
    'Use': 'uses',
    'Guide': 'guide',
    'Warning': 'warning',
    'Preserve': 'preserve',
    'Description': 'description',
    'Note': 'description_sale',
}

# Lens-specific fields (for product.lens model)
LENS_FIELD_MAP = {
    'SPH': 'sph',
    'CYL': 'cyl',
    'ADD': 'len_add',
    'AXIS': 'axis',
    'PRISM': 'prism',
    'PRISMBASE': 'prism_base',
    'BASE': 'base',
    'Abbe': 'abbe',
    'Polarized': 'polarized',
    'Diameter': 'diameter',
    'Design1': 'design1_id',
    'Design2': 'design2_id',
    'Material': 'material_id',
    'Index': 'index_id',
    'Uv': 'uv_id',
    'Coating': 'coating_ids',  # Many2many, CSV
    'HMC': 'cl_hmc_id',
    'PHO': 'cl_pho_id',
    'TIND': 'cl_tint_id',
    'ColorInt': 'color_int',
    'Corridor': 'corridor',
    'MirCoating': 'mir_coating',
}

# OPT-specific fields (for product.opt model)
OPT_FIELD_MAP = {
    'Sku': 'sku',
    'Model': 'model',
    'Model_Supplier': 'oem_ncc',
    'Serial': 'serial',
    'Color_Code': 'color_code',  # TODO: Add this field to product.opt
    'Season': 'season',
    'Frame': 'frame_id',
    'Gender': 'gender',
    'Frame_Type': 'frame_type_id',
    'Shape': 'shape_id',
    'Ve': 've_id',
    'Temple': 'temple_id',
    'Material_Ve': 'material_ve_id',
    'Material_TempleTip': 'material_temple_tip_id',
    'Material_Lens': 'material_lens_id',
    'Material_Opt_Front': 'materials_front_ids',  # Many2many, CSV
    'Material_Opt_Temple': 'materials_temple_ids',  # Many2many, CSV
    'Color_Lens': 'color_lens_id',
    'Coating': 'coating_ids',  # Many2many, CSV
    'Color_Opt_Front': 'color_front_id',
    'Color_Opt_Temple': 'color_temple_id',
    'Lens_Width': 'lens_width',
    'Bridge_Width': 'bridge_width',
    'Temple_Width': 'temple_width',
    'Lens_Height': 'lens_height',
    'Lens_Span': 'lens_span',
}

# Accessory-specific fields (for product.template with product_type='accessory')
# TODO: May need to create a separate model for accessories with these fields
ACCESSORY_FIELD_MAP = {
    'Design': 'design_id',
    'Shape': 'shape_id',
    'Material': 'material_id',
    'Color': 'color',
    'Width': 'width',
    'Length': 'length',
    'Height': 'height',
    'Head': 'head',
    'Body': 'body',
}

# Fields that are Many2many and need CSV parsing
M2M_FIELDS = {
    'Coating': 'coating_ids',
    'Accessory': 'accessory_ids',
    'Material_Opt_Front': 'materials_front_ids',
    'Material_Opt_Temple': 'materials_temple_ids',
}

# Required fields for each product type
REQUIRED_FIELDS = {
    'common': ['Group', 'FullName', 'TradeMark', 'Origin_Price'],
    'lens': [],
    'opt': ['Model'],
    'accessory': [],
}


def get_field_mapping(product_type):
    """
    Get combined field mapping for a product type
    
    Args:
        product_type: 'lens', 'opt', or 'accessory'
    
    Returns:
        dict: Combined mapping of Excel headers to Odoo fields
    """
    mapping = COMMON_FIELD_MAP.copy()
    
    if product_type == 'lens':
        mapping.update(LENS_FIELD_MAP)
    elif product_type == 'opt':
        mapping.update(OPT_FIELD_MAP)
    elif product_type == 'accessory':
        mapping.update(ACCESSORY_FIELD_MAP)
    
    return mapping


def get_required_fields(product_type):
    """
    Get list of required Excel headers for a product type
    
    Args:
        product_type: 'lens', 'opt', or 'accessory'
    
    Returns:
        list: Required field names (Excel headers)
    """
    required = REQUIRED_FIELDS['common'].copy()
    if product_type in REQUIRED_FIELDS:
        required.extend(REQUIRED_FIELDS[product_type])
    return required


def is_m2m_field(excel_header):
    """Check if an Excel header maps to a Many2many field"""
    return excel_header in M2M_FIELDS
