# -*- coding: utf-8 -*-
"""
Data validation for Excel import
"""
from . import field_mapper


def _normalize_text(value):
    if value in (None, False):
        return ''
    return ' '.join(str(value).strip().split())


def validate_required_fields(row_data, product_type):
    """
    Validate that all required fields are present
    
    Args:
        row_data: Dict of row data
        product_type: 'lens', 'opt', or 'accessory'
    
    Returns:
        list: List of error messages
    """
    errors = []
    required_fields = field_mapper.get_required_fields(product_type)
    
    for field in required_fields:
        if field not in row_data or not _normalize_text(row_data[field]):
            errors.append(f"Required field '{field}' is missing or empty")
    
    return errors


def validate_data_types(row_data, product_type):
    """
    Validate data types for numeric fields
    
    Args:
        row_data: Dict of row data
        product_type: 'lens', 'opt', or 'accessory'
    
    Returns:
        list: List of error messages
    """
    errors = []
    
    # Price fields that must be numeric
    price_fields = [
        'Origin_Price', 'Cost_Price', 'Retail_Price',
        'Wholesale_Price', 'Wholesale_Price_Max', 'Wholesale_Price_Min'
    ]
    
    for field in price_fields:
        if field in row_data and row_data[field]:
            try:
                float(row_data[field])
            except (ValueError, TypeError):
                errors.append(f"Field '{field}' must be a number, got: {row_data[field]}")
    
    # OPT dimension fields
    if product_type == 'opt':
        dimension_fields = [
            'Lens_Width', 'Bridge_Width', 'Temple_Width',
            'Lens_Height', 'Lens_Span'
        ]
        for field in dimension_fields:
            if field in row_data and row_data[field]:
                try:
                    int(row_data[field])
                except (ValueError, TypeError):
                    errors.append(f"Field '{field}' must be an integer, got: {row_data[field]}")
    
    # Accessory dimension fields
    if product_type == 'accessory':
        dimension_fields = ['Width', 'Length', 'Height', 'Head', 'Body']
        for field in dimension_fields:
            if field in row_data and row_data[field]:
                try:
                    float(row_data[field])
                except (ValueError, TypeError):
                    errors.append(f"Field '{field}' must be a number, got: {row_data[field]}")
    
    return errors


def validate_foreign_keys(cache, row_data, product_type):
    """
    Validate that foreign key values exist in master data
    
    Args:
        cache: MasterDataCache instance
        row_data: Dict of row data
        product_type: 'lens', 'opt', or 'accessory'
    
    Returns:
        list: List of error messages
    """
    errors = []
    
    # Common foreign keys
    fk_checks = [
        ('Group', cache.get_group, 'Product Group'),
        ('TradeMark', cache.get_brand, 'Brand'),
        ('Supplier', cache.get_supplier, 'Supplier'),
        ('Country', cache.get_country, 'Country'),
        ('Currency', cache.get_currency, 'Currency'),
        ('Warranty', cache.get_warranty, 'Warranty'),
        ('Supplier_Warranty', cache.get_warranty, 'Supplier Warranty'),
    ]
    
    for field_name, getter_func, display_name in fk_checks:
        if field_name in row_data and row_data[field_name]:
            value = row_data[field_name]
            record = getter_func(value)
            if not record:
                errors.append(f"{display_name} not found: '{value}'")
    
    # Lens-specific foreign keys
    if product_type == 'lens':
        lens_fk_checks = [
            ('Design1', cache.get_design, 'Design 1'),
            ('Design2', cache.get_design, 'Design 2'),
            ('Material', cache.get_lens_material, 'Lens Material'),
            ('Index', cache.get_lens_index, 'Lens Index'),
            ('Uv', cache.get_uv, 'UV'),
            ('HMC', cache.get_color, 'HMC Color'),
            ('PHO', cache.get_color, 'PHO Color'),
            ('TIND', cache.get_color, 'TIND Color'),
        ]
        
        for field_name, getter_func, display_name in lens_fk_checks:
            if field_name in row_data and row_data[field_name]:
                value = row_data[field_name]
                record = getter_func(value)
                if not record:
                    errors.append(f"{display_name} not found: '{value}'")
        
        # Coating (CSV)
        if 'Coating' in row_data and row_data['Coating']:
            coating_cids = str(row_data['Coating']).split(',')
            for coating_cid in coating_cids:
                coating_cid = coating_cid.strip()
                if coating_cid and not cache.get_coating(coating_cid):
                    errors.append(f"Coating not found: '{coating_cid}'")
    
    # OPT-specific foreign keys
    if product_type == 'opt':
        opt_fk_checks = [
            ('Frame', cache.get_frame, 'Frame'),
            ('Frame_Type', cache.get_frame_type, 'Frame Type'),
            ('Shape', cache.get_shape, 'Shape'),
            ('Ve', cache.get_ve, 'Ve'),
            ('Temple', cache.get_temple, 'Temple'),
            ('Material_Ve', cache.get_material, 'Ve Material'),
            ('Material_TempleTip', cache.get_material, 'Temple Tip Material'),
            ('Material_Lens', cache.get_material, 'Lens Material'),
            ('Color_Lens', cache.get_color, 'Lens Color'),
            ('Color_Opt_Front', cache.get_color, 'Front Color'),
            ('Color_Opt_Temple', cache.get_color, 'Temple Color'),
        ]
        
        for field_name, getter_func, display_name in opt_fk_checks:
            if field_name in row_data and row_data[field_name]:
                value = row_data[field_name]
                record = getter_func(value)
                if not record:
                    errors.append(f"{display_name} not found: '{value}'")
        
        # Material CSV fields
        csv_material_fields = [
            ('Material_Opt_Front', 'Front Material'),
            ('Material_Opt_Temple', 'Temple Material'),
        ]
        for field_name, display_name in csv_material_fields:
            if field_name in row_data and row_data[field_name]:
                material_cids = str(row_data[field_name]).split(',')
                for material_cid in material_cids:
                    material_cid = material_cid.strip()
                    if material_cid and not cache.get_material(material_cid):
                        errors.append(f"{display_name} not found: '{material_cid}'")
        
        # Coating (CSV)
        if 'Coating' in row_data and row_data['Coating']:
            coating_cids = str(row_data['Coating']).split(',')
            for coating_cid in coating_cids:
                coating_cid = coating_cid.strip()
                if coating_cid and not cache.get_coating(coating_cid):
                    errors.append(f"Coating not found: '{coating_cid}'")
    
    return errors


def validate_duplicates(env, rows):
    """
    Check for duplicate product names and codes within the import list
    and against existing products
    
    Args:
        env: Odoo environment
        rows: List of row data dicts
    
    Returns:
        list: List of error messages
    """
    # NOTE: Kept for backward compatibility with existing callers.
    return validate_duplicates_by_type(env, rows, product_type='opt')


def _build_duplicate_key(row, product_type):
    name = _normalize_text(row.get('FullName'))
    if not name:
        return None

    if product_type == 'lens':
        # Lens rows can share template name; include optical powers to avoid false positives.
        sph = _normalize_text(row.get('SPH'))
        cyl = _normalize_text(row.get('CYL'))
        add = _normalize_text(row.get('ADD'))
        axis = _normalize_text(row.get('AXIS'))
        prism = _normalize_text(row.get('PRISM'))
        prism_base = _normalize_text(row.get('PRISMBASE'))
        return ('lens', name.upper(), sph.upper(), cyl.upper(), add.upper(), axis.upper(), prism.upper(), prism_base.upper())

    # For opt/accessory we still guard by product name.
    return (product_type, name.upper())


def validate_duplicates_by_type(env, rows, product_type):
    """Validate duplicates with product-type-specific business keys."""
    errors = []
    seen_keys = {}

    # Check duplicates within import list
    for idx, row in enumerate(rows):
        duplicate_key = _build_duplicate_key(row, product_type)
        if not duplicate_key:
            continue

        excel_row = row.get('_excel_row', idx + 11)
        if duplicate_key in seen_keys:
            prev_row = seen_keys[duplicate_key]
            name = _normalize_text(row.get('FullName'))
            errors.append(
                f"Duplicate product key for '{name}' found in rows {prev_row} and {excel_row}"
            )
        else:
            seen_keys[duplicate_key] = excel_row

    # Existing database check by name for non-lens only.
    # Lens imports intentionally allow multiple rows with same template name for variant matrix.
    if product_type != 'lens':
        import_names = [_normalize_text(r.get('FullName')) for r in rows if _normalize_text(r.get('FullName'))]
        if import_names:
            existing = env['product.template'].search([
                ('name', 'in', import_names)
            ])
            existing_names = {(_normalize_text(p.name)).upper(): p.name for p in existing}

            for idx, row in enumerate(rows):
                name = _normalize_text(row.get('FullName'))
                if not name:
                    continue
                excel_row = row.get('_excel_row', idx + 11)
                if name.upper() in existing_names:
                    errors.append(
                        f"Product '{name}' already exists in database (row {excel_row})"
                    )

    return errors


def validate_all_rows(env, cache, rows, product_type):
    """
    Validate all rows and return comprehensive validation results
    
    Args:
        env: Odoo environment
        cache: MasterDataCache instance
        rows: List of row data dicts
        product_type: 'lens', 'opt', or 'accessory'
    
    Returns:
        dict: {
            'valid': bool,
            'errors': list of {'row': int, 'field': str, 'message': str},
            'warnings': list of {'row': int, 'field': str, 'message': str}
        }
    """
    all_errors = []
    all_warnings = []
    
    # Check for duplicates first
    dup_errors = validate_duplicates_by_type(env, rows, product_type)
    for error in dup_errors:
        all_errors.append({
            'row': None,
            'field': 'FullName',
            'message': error
        })
    
    # Validate each row
    for row in rows:
        excel_row = row.get('_excel_row', 'Unknown')
        
        # Required fields
        req_errors = validate_required_fields(row, product_type)
        for error in req_errors:
            all_errors.append({
                'row': excel_row,
                'field': None,
                'message': error
            })
        
        # Data types
        type_errors = validate_data_types(row, product_type)
        for error in type_errors:
            all_errors.append({
                'row': excel_row,
                'field': None,
                'message': error
            })
        
        # Foreign keys
        fk_errors = validate_foreign_keys(cache, row, product_type)
        for error in fk_errors:
            all_errors.append({
                'row': excel_row,
                'field': None,
                'message': error
            })
        
        # Warnings
        if 'Image' not in row or not row.get('Image'):
            all_warnings.append({
                'row': excel_row,
                'field': 'Image',
                'message': 'No image provided'
            })
    
    return {
        'valid': len(all_errors) == 0,
        'errors': all_errors,
        'warnings': all_warnings
    }
