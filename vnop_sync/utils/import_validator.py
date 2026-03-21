# -*- coding: utf-8 -*-
"""
Data validation for Excel import
"""
from . import field_mapper


FIELD_LABELS = {
    'Group': 'Nhóm sản phẩm',
    'FullName': 'Tên sản phẩm',
    'TradeMark': 'Thương hiệu',
    'Supplier': 'Nhà cung cấp',
    'Country': 'Quốc gia',
    'Currency': 'Tiền tệ',
    'Warranty': 'Bảo hành công ty',
    'Supplier_Warranty': 'Bảo hành nhà cung cấp',
    'Warranty_Retail': 'Bảo hành bán lẻ',
    'Unit': 'Đơn vị tính',
    'Accessory': 'Phụ kiện',
    'Origin_Price': 'Giá gốc',
    'Cost_Price': 'Giá vốn',
    'Retail_Price': 'Giá bán',
    'Wholesale_Price': 'Giá sỉ',
    'Wholesale_Price_Max': 'Giá sỉ tối đa',
    'Wholesale_Price_Min': 'Giá sỉ tối thiểu',
    'Image': 'Hình ảnh',
    'Design1': 'Thiết kế 1',
    'Design2': 'Thiết kế 2',
    'Material': 'Chất liệu',
    'Index': 'Chiết suất',
    'Uv': 'UV',
    'HMC': 'Màu HMC',
    'PHO': 'Màu PHO',
    'TIND': 'Màu TIND',
    'Coating': 'Lớp phủ',
    'Frame': 'Kiểu gọng',
    'Frame_Type': 'Loại gọng',
    'Shape': 'Dáng kính',
    'Ve': 'Vè',
    'Temple': 'Càng kính',
    'Material_Ve': 'Chất liệu vè',
    'Material_TempleTip': 'Chất liệu đuôi càng',
    'Material_Lens': 'Chất liệu tròng',
    'Material_Opt_Front': 'Chất liệu mặt trước',
    'Material_Opt_Temple': 'Chất liệu càng',
    'Color_Lens': 'Màu tròng',
    'Color_Opt_Front': 'Màu mặt trước',
    'Color_Opt_Temple': 'Màu càng',
    'Lens_Width': 'Chiều rộng tròng',
    'Bridge_Width': 'Chiều rộng cầu kính',
    'Temple_Width': 'Chiều dài càng',
    'Lens_Height': 'Chiều cao tròng',
    'Lens_Span': 'Độ rộng kính',
    'Width': 'Chiều rộng',
    'Length': 'Chiều dài',
    'Height': 'Chiều cao',
    'Head': 'Đầu',
    'Body': 'Thân',
}


def _field_label(field_code):
    return FIELD_LABELS.get(field_code, field_code)


def _fmt_required(field_code):
    return (
        f"Thiếu dữ liệu bắt buộc: {_field_label(field_code)} ({field_code}). "
        "Vui lòng kiểm tra lại file import."
    )


def _fmt_invalid(field_code, raw_value):
    return (
        f"{_field_label(field_code)} với giá trị '{raw_value}' ({field_code}) không hợp lệ. "
        "Vui lòng kiểm tra lại định dạng hoặc dữ liệu nhập."
    )


def _fmt_not_found(field_code, raw_value):
    return (
        f"{_field_label(field_code)} với giá trị '{raw_value}' ({field_code}) không tồn tại trong cơ sở dữ liệu. "
        "Vui lòng tạo trước hoặc nhập đúng giá trị hợp lệ."
    )


def _fmt_duplicate_key(name, prev_row, current_row):
    return (
        "Dữ liệu bị trùng theo tiêu chí nhận diện sản phẩm. "
        f"Sản phẩm '{name}' xuất hiện ở dòng {prev_row} và dòng {current_row}."
    )


def _fmt_existing_product(name, excel_row):
    return (
        "Sản phẩm với tiêu chí nhận diện hiện tại đã tồn tại trong hệ thống. "
        f"Tên sản phẩm: '{name}' (FullName), dòng {excel_row}."
    )


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
            errors.append(_fmt_required(field))
    
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
                errors.append(_fmt_invalid(field, row_data[field]))
    
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
                    errors.append(_fmt_invalid(field, row_data[field]))
    
    # Accessory dimension fields
    if product_type == 'accessory':
        dimension_fields = ['Width', 'Length', 'Height', 'Head', 'Body']
        for field in dimension_fields:
            if field in row_data and row_data[field]:
                try:
                    float(row_data[field])
                except (ValueError, TypeError):
                    errors.append(_fmt_invalid(field, row_data[field]))
    
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
        ('Group', cache.get_group),
        ('TradeMark', cache.get_brand),
        ('Supplier', cache.get_supplier),
        ('Country', cache.get_country),
        ('Currency', cache.get_currency),
        ('Warranty', cache.get_warranty),
        ('Supplier_Warranty', cache.get_warranty),
    ]
    
    for field_name, getter_func in fk_checks:
        if field_name in row_data and row_data[field_name]:
            value = row_data[field_name]
            record = getter_func(value)
            if not record:
                errors.append(_fmt_not_found(field_name, value))
    
    # Lens-specific foreign keys
    if product_type == 'lens':
        lens_fk_checks = [
            ('Design1', cache.get_design),
            ('Design2', cache.get_design),
            ('Material', cache.get_lens_material),
            ('Index', cache.get_lens_index),
            ('Uv', cache.get_uv),
            ('HMC', cache.get_color),
            ('PHO', cache.get_color),
            ('TIND', cache.get_color),
        ]
        
        for field_name, getter_func in lens_fk_checks:
            if field_name in row_data and row_data[field_name]:
                value = row_data[field_name]
                record = getter_func(value)
                if not record:
                    errors.append(_fmt_not_found(field_name, value))
        
        # Coating (CSV)
        if 'Coating' in row_data and row_data['Coating']:
            coating_cids = str(row_data['Coating']).split(',')
            for coating_cid in coating_cids:
                coating_cid = coating_cid.strip()
                if coating_cid and not cache.get_coating(coating_cid):
                    errors.append(_fmt_not_found('Coating', coating_cid))
    
    # OPT-specific foreign keys
    if product_type == 'opt':
        opt_fk_checks = [
            ('Frame', cache.get_frame),
            ('Frame_Type', cache.get_frame_type),
            ('Shape', cache.get_shape),
            ('Ve', cache.get_ve),
            ('Temple', cache.get_temple),
            ('Material_Ve', cache.get_material),
            ('Material_TempleTip', cache.get_material),
            ('Material_Lens', cache.get_material),
            ('Color_Lens', cache.get_color),
            ('Color_Opt_Front', cache.get_color),
            ('Color_Opt_Temple', cache.get_color),
        ]
        
        for field_name, getter_func in opt_fk_checks:
            if field_name in row_data and row_data[field_name]:
                value = row_data[field_name]
                record = getter_func(value)
                if not record:
                    errors.append(_fmt_not_found(field_name, value))
        
        # Material CSV fields
        csv_material_fields = ['Material_Opt_Front', 'Material_Opt_Temple']
        for field_name in csv_material_fields:
            if field_name in row_data and row_data[field_name]:
                material_cids = str(row_data[field_name]).split(',')
                for material_cid in material_cids:
                    material_cid = material_cid.strip()
                    if material_cid and not cache.get_material(material_cid):
                        errors.append(_fmt_not_found(field_name, material_cid))
        
        # Coating (CSV)
        if 'Coating' in row_data and row_data['Coating']:
            coating_cids = str(row_data['Coating']).split(',')
            for coating_cid in coating_cids:
                coating_cid = coating_cid.strip()
                if coating_cid and not cache.get_coating(coating_cid):
                    errors.append(_fmt_not_found('Coating', coating_cid))
    
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
                _fmt_duplicate_key(name, prev_row, excel_row)
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
                        _fmt_existing_product(name, excel_row)
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
                'message': 'Không có hình ảnh cho dòng dữ liệu này (Image). Bạn vẫn có thể import nếu không bắt buộc ảnh.'
            })
    
    return {
        'valid': len(all_errors) == 0,
        'errors': all_errors,
        'warnings': all_warnings
    }
