# -*- coding: utf-8 -*-

import base64
import json
import logging
import re
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from ..utils import excel_reader, data_cache, import_validator, excel_template_generator, product_code_utils, lens_variant_utils

_logger = logging.getLogger(__name__)


PREVIEW_COMMON_FIELD_MAP = [
    ('group', 'Group', 'text'),
    ('image', 'Image', 'binary'),
    ('full_name', 'FullName', 'text'),
    ('eng_name', 'EngName', 'text'),
    ('trade_name', 'TradeName', 'text'),
    ('unit', 'Unit', 'text'),
    ('brand', 'TradeMark', 'text'),
    ('supplier', 'Supplier', 'text'),
    ('country', 'Country', 'text'),
    ('supplier_warranty', 'Supplier_Warranty', 'text'),
    ('warranty', 'Warranty', 'text'),
    ('warranty_retail', 'Warranty_Retail', 'text'),
    ('accessory', 'Accessory', 'text'),
    ('origin_price', 'Origin_Price', 'float'),
    ('currency', 'Currency', 'text'),
    ('cost_price', 'Cost_Price', 'float'),
    ('retail_price', 'Retail_Price', 'float'),
    ('wholesale_price', 'Wholesale_Price', 'float'),
    ('wholesale_price_max', 'Wholesale_Price_Max', 'float'),
    ('wholesale_price_min', 'Wholesale_Price_Min', 'float'),
    ('use', 'Use', 'text'),
    ('guide', 'Guide', 'text'),
    ('warning', 'Warning', 'text'),
    ('preserve', 'Preserve', 'text'),
    ('description', 'Description', 'text'),
    ('note', 'Note', 'text'),
]

PREVIEW_TYPE_FIELD_MAP = {
    'lens': [
        ('sph', 'SPH', 'text'),
        ('cyl', 'CYL', 'text'),
        ('add', 'ADD', 'text'),
        ('axis', 'AXIS', 'text'),
        ('prism', 'PRISM', 'text'),
        ('prismbase', 'PRISMBASE', 'text'),
        ('lens_base', 'BASE', 'text'),
        ('abbe', 'Abbe', 'text'),
        ('polarized', 'Polarized', 'text'),
        ('diameter', 'Diameter', 'text'),
        ('design1', 'Design1', 'text'),
        ('design2', 'Design2', 'text'),
        ('lens_material', 'Material', 'text'),
        ('index', 'Index', 'text'),
        ('uv', 'Uv', 'text'),
        ('lens_coating', 'Coating', 'text'),
        ('hmc', 'HMC', 'text'),
        ('pho', 'PHO', 'text'),
        ('tind', 'TIND', 'text'),
        ('color_int', 'ColorInt', 'text'),
        ('corridor', 'Corridor', 'text'),
        ('mir_coating', 'MirCoating', 'text'),
    ],
    'opt': [
        ('sku', 'Sku', 'text'),
        ('model', 'Model', 'text'),
        ('model_supplier', 'Model_Supplier', 'text'),
        ('serial', 'Serial', 'text'),
        ('color_code', 'Color_Code', 'text'),
        ('season', 'Season', 'text'),
        ('frame', 'Frame', 'text'),
        ('gender', 'Gender', 'text'),
        ('frame_type', 'Frame_Type', 'text'),
        ('opt_shape', 'Shape', 'text'),
        ('ve', 'Ve', 'text'),
        ('temple', 'Temple', 'text'),
        ('material_ve', 'Material_Ve', 'text'),
        ('material_temple_tip', 'Material_TempleTip', 'text'),
        ('material_lens', 'Material_Lens', 'text'),
        ('material_opt_front', 'Material_Opt_Front', 'text'),
        ('material_opt_temple', 'Material_Opt_Temple', 'text'),
        ('color_lens', 'Color_Lens', 'text'),
        ('opt_coating', 'Coating', 'text'),
        ('color_opt_front', 'Color_Opt_Front', 'text'),
        ('color_opt_temple', 'Color_Opt_Temple', 'text'),
        ('lens_width', 'Lens_Width', 'text'),
        ('bridge_width', 'Bridge_Width', 'text'),
        ('temple_width', 'Temple_Width', 'text'),
        ('lens_height', 'Lens_Height', 'text'),
        ('lens_span', 'Lens_Span', 'text'),
    ],
    'accessory': [
        ('design', 'Design', 'text'),
        ('accessory_shape', 'Shape', 'text'),
        ('accessory_material', 'Material', 'text'),
        ('accessory_color', 'Color', 'text'),
        ('width', 'Width', 'text'),
        ('length', 'Length', 'text'),
        ('height', 'Height', 'text'),
        ('head', 'Head', 'text'),
        ('body', 'Body', 'text'),
    ],
}


class ProductExcelImport(models.TransientModel):
    _name = 'product.excel.import'
    _description = 'Import Products from Excel'
    
    # File upload
    excel_file = fields.Binary(
        string='Excel File',
        help='Upload Excel file with product data'
    )
    file_name = fields.Char('File Name')
    
    # Auto-detected product type
    product_type = fields.Selection([
        ('lens', 'Lens'),
        ('opt', 'Optical Product'),
        ('accessory', 'Accessory')
    ], string='Product Type', readonly=True)
    
    # Preview data (One2many for table view with pagination)
    preview_line_ids = fields.One2many(
        'product.excel.preview.line',
        'wizard_id',
        string='Preview Lines',
        readonly=True
    )
    
    # Keep JSON for debugging
    preview_data = fields.Text(
        string='Preview Data',
        readonly=True,
        help='Parsed data from Excel file in JSON format'
    )
    
    # Wizard state
    state = fields.Selection([
        ('upload', 'Upload File'),
        ('preview', 'Preview Data'),
        ('done', 'Import Complete')
    ], string='State', default='upload')
    
    # Results
    success_count = fields.Integer('Successful Imports', readonly=True, default=0)
    error_count = fields.Integer('Errors', readonly=True, default=0)
    error_log = fields.Text('Error Log', readonly=True)
    
    # Template download selection
    template_type = fields.Selection([
        ('lens', 'Mẫu Mắt (Lens)'),
        ('opt', 'Mẫu Gọng/Kính'),
        ('accessory', 'Mẫu Phụ kiện'),
    ], string='Tải mẫu nhập liệu')
    
    # Employee assignment
    employee_id = fields.Many2one(
        'hr.employee',
        string='Nhân viên phụ trách',
        help='Assign all imported products to this employee'
    )
    
    @api.onchange('template_type')
    def _onchange_template_type(self):
        """Auto download template when selection changes"""
        if self.template_type:
            # Reset selection after download
            template_type = self.template_type
            self.template_type = False
            
            try:
                if template_type == 'lens':
                    template_data = excel_template_generator.generate_lens_template()
                    filename = f"BangNhap_Mat_{datetime.now().strftime('%Y%m%d')}.xlsx"
                elif template_type == 'opt':
                    template_data = excel_template_generator.generate_opt_template()
                    filename = f"BangNhap_Gong_{datetime.now().strftime('%Y%m%d')}.xlsx"
                elif template_type == 'accessory':
                    template_data = excel_template_generator.generate_accessory_template()
                    filename = f"BangNhap_PhuKien_{datetime.now().strftime('%Y%m%d')}.xlsx"
                else:
                    return
                
                # Create attachment
                attachment = self.env['ir.attachment'].create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(template_data),
                    'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                })
                
                # Return download action
                return {
                    'type': 'ir.actions.act_url',
                    'url': f'/web/content/{attachment.id}?download=true',
                    'target': 'new',
                }
            except Exception as e:
                _logger.error(f"Error generating template: {e}", exc_info=True)
                return {
                    'warning': {
                        'title': 'Lỗi',
                        'message': f'Không thể tạo mẫu: {str(e)}'
                    }
                }
    
    # ===========================================
    # DOWNLOAD TEMPLATE ACTIONS
    # ===========================================
    
    def action_download_lens_template(self):
        """Download Excel template for Lens products"""
        self.ensure_one()
        try:
            template_data = excel_template_generator.generate_lens_template()
            filename = f"BangNhap_Mat_{datetime.now().strftime('%Y%m%d')}.xlsx"
            return self._create_download_action(template_data, filename)
        except Exception as e:
            _logger.error(f"Error generating lens template: {e}", exc_info=True)
            raise UserError(_('Error generating template: %s') % str(e))
    
    def action_download_opt_template(self):
        """Download Excel template for Optical products"""
        self.ensure_one()
        try:
            template_data = excel_template_generator.generate_opt_template()
            filename = f"BangNhap_Gong_{datetime.now().strftime('%Y%m%d')}.xlsx"
            return self._create_download_action(template_data, filename)
        except Exception as e:
            _logger.error(f"Error generating optical template: {e}", exc_info=True)
            raise UserError(_('Error generating template: %s') % str(e))
    
    def action_download_accessory_template(self):
        """Download Excel template for Accessory products"""
        self.ensure_one()
        try:
            template_data = excel_template_generator.generate_accessory_template()
            filename = f"BangNhap_PhuKien_{datetime.now().strftime('%Y%m%d')}.xlsx"
            return self._create_download_action(template_data, filename)
        except Exception as e:
            _logger.error(f"Error generating accessory template: {e}", exc_info=True)
            raise UserError(_('Error generating template: %s') % str(e))
    
    def _create_download_action(self, file_data, filename):
        """Create download action for Excel file"""
        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(file_data),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
    
    
    def action_parse_excel(self):
        """
        Parse uploaded Excel file and move to preview state
        """
        self.ensure_one()
        
        if not self.excel_file:
            raise UserError(_('Please upload an Excel file first.'))
        
        try:
            # Decode file
            file_content = base64.b64decode(self.excel_file)
            
            # Parse Excel
            parsed_data = excel_reader.parse_excel_file(file_content, self.file_name or 'uploaded.xlsx')
            
            # Set product type
            self.product_type = parsed_data['product_type']
            
            # Validate data
            cache = data_cache.MasterDataCache(self.env)
            validation_result = import_validator.validate_all_rows(
                self.env,
                cache,
                parsed_data['rows'],
                parsed_data['product_type']
            )
            
            # Clear existing preview lines
            self.preview_line_ids.unlink()
            
            # Create preview lines with auto-generated codes
            preview_lines = self._generate_preview_lines(
                parsed_data['rows'],
                parsed_data['product_type'],
                cache,
                validation_result
            )
            self.preview_line_ids = preview_lines
            
            # Keep JSON for debugging
            preview = {
                'product_type': parsed_data['product_type'],
                'total_rows': parsed_data['total_rows'],
                'headers': parsed_data['headers'],
                'validation': {
                    'valid': validation_result['valid'],
                    'error_count': len(validation_result['errors']),
                    'warning_count': len(validation_result['warnings']),
                }
            }
            self.preview_data = json.dumps(preview, indent=2, ensure_ascii=False)
            
            # Format error log
            if validation_result['errors'] or validation_result['warnings']:
                error_lines = []
                
                if validation_result['errors']:
                    error_lines.append('ERRORS:')
                    error_lines.append('=' * 60)
                    for err in validation_result['errors']:
                        row_info = f"Row {err['row']}: " if err['row'] else ""
                        error_lines.append(f"  {row_info}{err['message']}")
                
                if validation_result['warnings']:
                    error_lines.append('\nWARNINGS:')
                    error_lines.append('=' * 60)
                    for warn in validation_result['warnings']:
                        row_info = f"Row {warn['row']}: " if warn['row'] else ""
                        error_lines.append(f"  {row_info}{warn['message']}")
                
                self.error_log = '\n'.join(error_lines)
            else:
                self.error_log = False
            
            # Store full data in context for import (temporary solution)
            # In production, might want to use ir.attachment or database storage
            self = self.with_context(parsed_excel_data=parsed_data)
            
            # Move to preview state
            self.state = 'preview'
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'product.excel.import',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'parsed_excel_data': parsed_data}
            }
        
        except Exception as e:
            _logger.error(f"Error parsing Excel file: {str(e)}", exc_info=True)
            raise UserError(_('Error parsing Excel file: %s') % str(e))
    
    def action_back_to_upload(self):
        self.ensure_one()
        self.state = 'upload'
        self.error_log = False
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.excel.import',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_confirm_import(self):
        """
        Import products into database using batch processing for optimal performance.
        
        Optimizations:
        - Batch create: Creates all products in batches instead of one-by-one
        - Disabled tracking: Turns off mail/activity tracking during import
        - Pre-generated codes: Generates all product codes before creating products
        - Batch commits: Commits every BATCH_SIZE records to avoid long locks
        """
        self.ensure_one()
        
        BATCH_SIZE = 100  # Commit every 100 records
        
        # Get parsed data from context (temporary solution)
        parsed_data = self.env.context.get('parsed_excel_data')
        if not parsed_data:
            # Try to re-parse if data lost
            _logger.warning("Parsed data not found in context, re-parsing...")
            file_content = base64.b64decode(self.excel_file)
            parsed_data = excel_reader.parse_excel_file(file_content, self.file_name or 'uploaded.xlsx')
        
        # Validate again
        cache = data_cache.MasterDataCache(self.env)
        validation_result = import_validator.validate_all_rows(
            self.env,
            cache,
            parsed_data['rows'],
            parsed_data['product_type']
        )
        
        if not validation_result['valid']:
            raise UserError(_(
                'Cannot import: Data validation failed. Please fix errors and try again.\n\n'
                'See Error Log tab for details.'
            ))
        
        # Apply optimization context flags
        optimized_self = self.with_context(
            tracking_disable=True,
            mail_notrack=True,
            mail_create_nolog=True,
            no_reset_password=True,
            import_mode=True,
            prefetch_fields=False,
        )
        
        rows = parsed_data['rows']
        product_type = parsed_data['product_type']
        total_rows = len(rows)
        
        _logger.info(f"Starting batch import of {total_rows} {product_type} products...")
        
        success_count = 0
        error_count = 0
        error_messages = []
        
        try:
            # Process in batches
            for batch_start in range(0, total_rows, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_rows)
                batch_rows = rows[batch_start:batch_end]
                batch_num = (batch_start // BATCH_SIZE) + 1
                total_batches = (total_rows + BATCH_SIZE - 1) // BATCH_SIZE
                
                _logger.info(f"Processing batch {batch_num}/{total_batches} (rows {batch_start + 1}-{batch_end})")
                
                try:
                    with optimized_self.env.cr.savepoint():
                        created_count = optimized_self._create_products_batch(
                            batch_rows, product_type, cache
                        )
                        success_count += created_count
                    
                    # Commit after successful batch
                    optimized_self.env.cr.commit()
                    _logger.info(f"Batch {batch_num} committed: {created_count} products created")
                    
                except Exception as e:
                    error_count += len(batch_rows)
                    error_messages.append(f"Batch {batch_num} failed: {str(e)}")
                    _logger.error(f"Error in batch {batch_num}: {str(e)}", exc_info=True)
                    # Continue with next batch
            
            if error_count > 0 and success_count == 0:
                raise UserError(_(
                    'Import failed completely. All batches had errors.\n\n%s'
                ) % '\n'.join(error_messages[:10]))
        
        except Exception as e:
            self.error_log = str(e)
            self.error_count = error_count
            raise
        
        # Success (possibly partial)
        self.success_count = success_count
        self.error_count = error_count
        
        if error_count > 0:
            self.error_log = f"Imported {success_count} products with {error_count} errors:\n" + '\n'.join(error_messages[:10])
        else:
            self.error_log = f"Successfully imported {success_count} products!"
        
        self.state = 'done'
        
        _logger.info(f"Import completed: {success_count} success, {error_count} errors")
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.excel.import',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def _generate_preview_lines(self, rows, product_type, cache, validation_result):
        """Generate preview lines from parsed Excel data"""
        
        preview_lines = []
        error_dict = {}
        
        # Build error dictionary by row number
        for err in validation_result.get('errors', []):
            row = err.get('row')
            if row:
                if row not in error_dict:
                    error_dict[row] = []
                error_dict[row].append(err['message'])
        
        for idx, row_data in enumerate(rows, start=1):
            # Get group and brand for code generation
            group = cache.get_group(row_data.get('Group'))
            brand = cache.get_brand(row_data.get('TradeMark'))
            
            # Get lens index for lens products
            lens_index_id = False
            if product_type == 'lens' and row_data.get('Index'):
                index_record = cache.get_lens_index(row_data['Index'])
                if index_record:
                    lens_index_id = index_record.id
            
            # Generate code
            generated_code = ''
            if group and brand:
                try:
                    generated_code = product_code_utils.generate_product_code(
                        self.env,
                        group.id,
                        brand.id,
                        lens_index_id
                    )
                except Exception as e:
                    _logger.warning(f"Could not generate code for row {idx}: {e}")
                    generated_code = f"ERROR: {str(e)[:30]}"
            else:
                generated_code = 'Thiếu Nhóm/Thương hiệu'
            
            line_vals = {
                'row_number': idx,
                'generated_code': generated_code,
            }
            line_vals.update(self._build_preview_field_values(row_data, PREVIEW_COMMON_FIELD_MAP))
            line_vals.update(self._build_preview_field_values(
                row_data,
                PREVIEW_TYPE_FIELD_MAP.get(product_type, [])
            ))
            
            # Add errors if any
            excel_row = row_data.get('_excel_row', idx)
            if excel_row in error_dict:
                line_vals['has_error'] = True
                line_vals['error_message'] = '\n'.join(error_dict[excel_row])
            
            preview_lines.append((0, 0, line_vals))
        
        return preview_lines

    def _build_preview_field_values(self, row_data, field_map):
        values = {}
        for preview_field, excel_field, value_type in field_map:
            raw_value = row_data.get(excel_field)
            if value_type == 'float':
                values[preview_field] = self._safe_preview_float(raw_value)
            elif value_type == 'binary':
                values[preview_field] = raw_value or False
            else:
                values[preview_field] = raw_value or ''
        return values

    def _safe_preview_float(self, value):
        if value in (None, '', False):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    
    def _create_products_batch(self, rows, product_type, cache):
        """
        Create multiple products at once using batch operations.
        
        This is much faster than creating products one by one because:
        - Uses batch code generation (1 query per prefix instead of per product)
        - Uses Odoo's batch create (1 insert per batch instead of per product)
        - Pre-processes all data before any database operations
        
        Args:
            rows: List of row data dictionaries
            product_type: 'lens', 'opt', or 'accessory'
            cache: MasterDataCache instance
            
        Returns:
            Number of successfully created products
        """
        if not rows:
            return 0

        if product_type == 'lens':
            return self._create_lens_variants_from_rows(rows, cache)
        
        # Phase 1: Prepare code generation requests
        code_requests = []
        for row_data in rows:
            group = cache.get_group(row_data.get('Group'))
            brand = cache.get_brand(row_data.get('TradeMark'))
            
            lens_index_id = False
            if product_type == 'lens' and row_data.get('Index'):
                index_record = cache.get_lens_index(row_data['Index'])
                if index_record:
                    lens_index_id = index_record.id
            
            code_requests.append((
                group.id if group else None,
                brand.id if brand else None,
                lens_index_id
            ))
        
        # Phase 2: Generate all codes at once
        generated_codes = product_code_utils.generate_product_codes_batch(
            self.env, code_requests
        )
        
        # Phase 3: Prepare all product vals
        all_product_vals = []
        for idx, row_data in enumerate(rows):
            product_vals = self._prepare_product_vals(row_data, product_type, cache)
            
            # Apply generated code
            if generated_codes[idx]:
                product_vals['default_code'] = generated_codes[idx]
            
            all_product_vals.append(product_vals)
        
        # Phase 4: Batch create products
        products = self.env['product.template'].create(all_product_vals)

        # Phase 5: Upsert vendor lines from Excel without creating duplicates on re-import.
        for product, row_data in zip(products, rows):
            self._upsert_supplierinfo(product, row_data, cache)
        
        _logger.debug(f"Batch created {len(products)} products")
        
        return len(products)

    def _resolve_lens_coating_ids_from_row(self, row_data, cache):
        raw = row_data.get('Coating') or row_data.get('Coatings') or ''
        if not raw:
            return [], []

        parts = [p.strip() for p in str(raw).split(',') if p.strip()]
        coating_ids = []
        coating_codes = []
        for code in parts:
            coating_codes.append(code)
            rec = cache.get_coating(code)
            if rec:
                coating_ids.append(rec.id)
        return coating_ids, coating_codes

    def _build_lens_template_key_from_row(self, row_data, coating_codes):
        cid = row_data.get('CID') or row_data.get('Cid') or row_data.get('ID') or row_data.get('Id') or ''
        index_code = row_data.get('Index') or ''
        material_code = row_data.get('Material') or ''
        diameter = row_data.get('Diameter') or ''
        brand_code = row_data.get('TradeMark') or ''
        return lens_variant_utils.build_lens_template_key(
            cid, index_code, material_code, coating_codes, diameter, brand_code
        )

    def _get_or_create_lens_template_from_row(self, row_data, cache):
        coating_ids, coating_codes = self._resolve_lens_coating_ids_from_row(row_data, cache)
        template_key = self._build_lens_template_key_from_row(row_data, coating_codes)

        tmpl = self.env['product.template'].search(
            [('lens_template_key', '=', template_key)], limit=1
        )

        vals = self._prepare_product_vals(row_data, 'lens', cache, use_lens_ids=False)
        vals['lens_template_key'] = template_key
        vals.update(self._prepare_lens_template_vals(row_data, cache, coating_ids=coating_ids))

        if tmpl:
            tmpl.write(vals)
            self._upsert_supplierinfo(tmpl, row_data, cache)
            return tmpl

        tmpl = self.env['product.template'].create(vals)
        self._upsert_supplierinfo(tmpl, row_data, cache)
        return tmpl

    def _get_or_create_lens_variant_from_row(self, template, row_data, cache=None):
        sph = lens_variant_utils.format_power_value(row_data.get('SPH'))
        cyl = lens_variant_utils.format_power_value(row_data.get('CYL'))
        if not sph or not cyl:
            return False

        add_raw = row_data.get('ADD')
        add_val = lens_variant_utils.format_power_value(add_raw)

        attr_sph = lens_variant_utils.get_or_create_attribute(self.env, 'SPH')
        attr_cyl = lens_variant_utils.get_or_create_attribute(self.env, 'CYL')
        attr_add = lens_variant_utils.get_or_create_attribute(self.env, 'ADD') if add_val else False

        val_sph = lens_variant_utils.get_or_create_attribute_value(self.env, attr_sph, sph)
        val_cyl = lens_variant_utils.get_or_create_attribute_value(self.env, attr_cyl, cyl)
        val_add = lens_variant_utils.get_or_create_attribute_value(self.env, attr_add, add_val) if attr_add else False

        lens_variant_utils.ensure_attribute_line(template, attr_sph, [val_sph.id])
        lens_variant_utils.ensure_attribute_line(template, attr_cyl, [val_cyl.id])
        if attr_add and val_add:
            lens_variant_utils.ensure_attribute_line(template, attr_add, [val_add.id])

        value_ids = [val_sph.id, val_cyl.id]
        if val_add:
            value_ids.append(val_add.id)

        variant = lens_variant_utils.find_variant_by_values(template, value_ids)
        if variant:
            return variant

        return lens_variant_utils.create_variant(template, value_ids)

    def _create_lens_record_for_variant(self, variant, row_data, cache):
        """Create/update product.lens record for a variant"""
        if not variant:
            return None
        
        lens_vals = self._prepare_lens_vals(row_data, cache)
        lens_vals['product_id'] = variant.id
        lens_vals['product_tmpl_id'] = variant.product_tmpl_id.id
        
        # Find or create lens record for this variant
        existing_lens = self.env['product.lens'].search(
            [('product_id', '=', variant.id)], limit=1
        )
        
        if existing_lens:
            existing_lens.write(lens_vals)
            return existing_lens
        
        return self.env['product.lens'].create(lens_vals)
    
    def _create_lens_variants_from_rows(self, rows, cache):
        created_count = 0

        for row_data in rows:
            tmpl = self._get_or_create_lens_template_from_row(row_data, cache)
            variant = self._get_or_create_lens_variant_from_row(tmpl, row_data, cache)
            if not variant:
                continue
            
            created_count += 1

        return created_count
    
    def _prepare_product_vals(self, row_data, product_type, cache, use_lens_ids=True):
        """
        Prepare product values dictionary from row data.
        Extracted from _create_product for reuse in batch operations.
        """
        product_vals = {
            'name': row_data.get('FullName'),
            'x_eng_name': row_data.get('EngName'),
            'x_trade_name': row_data.get('TradeName'),
            'product_type': product_type,
            'type': 'consu',
        }
        
        # Group (required)
        group = cache.get_group(row_data.get('Group'))
        if group:
            product_vals['group_id'] = group.id

        categ_id = self._resolve_category_id(product_type, group)
        if categ_id:
            product_vals['categ_id'] = categ_id
        
        # Brand (required)
        brand = cache.get_brand(row_data.get('TradeMark'))
        if brand:
            product_vals['brand_id'] = brand.id
        
        # Optional foreign keys
        
        if row_data.get('Country'):
            country = cache.get_country(row_data['Country'])
            if country:
                product_vals['country_id'] = country.id
        
        # Always pass explicit value to avoid user/company default warranty leaking into imports.
        product_vals['warranty_id'] = False
        if row_data.get('Warranty'):
            warranty = cache.get_warranty(row_data['Warranty'])
            if warranty:
                product_vals['warranty_id'] = warranty.id
        
        if row_data.get('Currency'):
            currency = cache.get_currency(row_data['Currency'])
            if currency:
                product_vals['x_currency_zone_code'] = currency.name
        
        # Prices
        product_vals['standard_price'] = float(row_data.get('Cost_Price', 0) or 0)
        product_vals['list_price'] = float(row_data.get('Retail_Price', 0) or 0)
        product_vals['x_ws_price'] = float(row_data.get('Wholesale_Price', 0) or 0)
        product_vals['x_ws_price_max'] = float(row_data.get('Wholesale_Price_Max', 0) or 0)
        product_vals['x_ws_price_min'] = float(row_data.get('Wholesale_Price_Min', 0) or 0)
        
        # Text fields
        if row_data.get('Use'):
            product_vals['x_uses'] = row_data['Use']
        if row_data.get('Guide'):
            product_vals['x_guide'] = row_data['Guide']
        if row_data.get('Warning'):
            product_vals['x_warning'] = row_data['Warning']
        if row_data.get('Preserve'):
            product_vals['x_preserve'] = row_data['Preserve']
        if row_data.get('Description'):
            product_vals['description'] = row_data['Description']
        if row_data.get('Note'):
            product_vals['description_sale'] = row_data['Note']

        # Common columns that map to existing technical fields on product.template.
        if row_data.get('Unit'):
            uom_id = self._resolve_uom_id(row_data['Unit'])
            if uom_id:
                product_vals['uom_id'] = uom_id
                product_vals['uom_po_id'] = uom_id

        if row_data.get('Supplier_Warranty'):
            product_vals['manufacturer_months'] = self._parse_warranty_months(
                row_data['Supplier_Warranty'], cache=cache
            )

        if row_data.get('Warranty_Retail'):
            product_vals['bao_hanh_ban_le'] = self._parse_warranty_months(
                row_data['Warranty_Retail'], cache=cache
            )

        if row_data.get('Accessory'):
            product_vals['x_accessory_total'] = self._parse_accessory_total(
                row_data['Accessory']
            )
        
        # Employee assignment
        if self.employee_id:
            product_vals['employee_id'] = self.employee_id.id
        
        # Image
        if row_data.get('Image'):
            product_vals['image_1920'] = row_data['Image']

        # Template-level business mapping by product type
        if product_type == 'lens':
            product_vals.update(self._prepare_lens_template_vals(row_data, cache))
        elif product_type == 'opt':
            product_vals.update(self._prepare_opt_template_vals(row_data, cache))
        elif product_type == 'accessory':
            product_vals.update(self._prepare_accessory_template_vals(row_data, cache))
        
        return product_vals

    def _safe_int_from_text(self, value):
        """Parse integer-like values from Excel text (e.g. '72mm', '70/28mm')."""
        if value in (None, '', False):
            return 0
        if isinstance(value, (int, float)):
            return int(value)

        text = str(value).strip()
        if not text:
            return 0

        match = re.search(r'\d+', text)
        if match:
            return int(match.group(0))
        return 0
    
    def _safe_float_from_text(self, value):
        """Parse float-like values from Excel text (e.g. '1.50', '+1.50', '-0.75')."""
        if value in (None, '', False):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        if not text:
            return 0.0

        try:
            return float(text)
        except (ValueError, TypeError):
            # Try to extract first numeric pattern
            match = re.search(r'[-+]?\d+\.?\d*', text)
            if match:
                try:
                    return float(match.group(0))
                except (ValueError, TypeError):
                    pass
        return 0.0

    def _parse_non_negative_float(self, value, default=0.0):
        parsed = self._safe_float_from_text(value)
        return parsed if parsed >= 0 else default

    def _parse_positive_int(self, value, default=1):
        parsed = self._safe_int_from_text(value)
        return parsed if parsed > 0 else default

    def _extract_supplier_terms(self, row_data):
        """Extract vendor terms with resilient defaults for files without explicit columns."""
        min_qty_raw = (
            row_data.get('Min_Qty')
            or row_data.get('MinQty')
            or row_data.get('MOQ')
            or row_data.get('Minimum_Qty')
        )
        delay_raw = (
            row_data.get('Delay')
            or row_data.get('Lead_Time')
            or row_data.get('LeadTime')
        )
        return {
            'price': self._parse_non_negative_float(row_data.get('Origin_Price'), default=0.0),
            'min_qty': float(self._parse_positive_int(min_qty_raw, default=1)),
            'delay': self._parse_positive_int(delay_raw, default=1),
        }

    def _upsert_supplierinfo(self, product_tmpl, row_data, cache):
        """Upsert a single vendor line for a product.template based on import row."""
        supplier_code = row_data.get('Supplier')
        if not supplier_code:
            return

        supplier = cache.get_supplier(supplier_code)
        if not supplier:
            return

        currency_id = False
        if row_data.get('Currency'):
            currency = cache.get_currency(row_data['Currency'])
            currency_id = currency.id if currency else False

        terms = self._extract_supplier_terms(row_data)
        seller_domain = [
            ('product_tmpl_id', '=', product_tmpl.id),
            ('product_id', '=', False),
            ('partner_id', '=', supplier.id),
            ('min_qty', '=', terms['min_qty']),
            ('delay', '=', terms['delay']),
            ('currency_id', '=', currency_id),
        ]
        seller = self.env['product.supplierinfo'].search(seller_domain, limit=1)

        seller_vals = {
            'partner_id': supplier.id,
            'product_tmpl_id': product_tmpl.id,
            'product_id': False,
            'price': terms['price'],
            'min_qty': terms['min_qty'],
            'delay': terms['delay'],
            'currency_id': currency_id,
        }

        if seller:
            # Keep one line per unique vendor key, update price/terms when re-importing.
            seller.write(seller_vals)
            return

        self.env['product.supplierinfo'].create(seller_vals)

    def _resolve_uom_id(self, unit_name):
        """Resolve a Unit string from Excel to uom.uom id."""
        if unit_name in (None, '', False):
            return False

        name = str(unit_name).strip()
        if not name:
            return False

        uom_model = self.env['uom.uom']
        uom = uom_model.search([('name', '=', name)], limit=1)
        if not uom:
            uom = uom_model.search([('name', 'ilike', name)], limit=1)
        return uom.id if uom else False

    def _parse_warranty_months(self, raw_value, cache=None):
        """Parse warranty input to integer months.

        Accepts direct number text (e.g. '12', '12 tháng') or a warranty code/name.
        Warranty master value is in days, so convert to months when resolving by code.
        """
        if raw_value in (None, '', False):
            return 0

        months = self._safe_int_from_text(raw_value)
        if months:
            return months

        if cache:
            warranty = cache.get_warranty(raw_value)
            if warranty:
                days = int(warranty.value or 0)
                if days <= 0:
                    return 0
                return max(1, round(days / 30.0))

        return 0

    def _parse_accessory_total(self, raw_value):
        """Parse Accessory column to integer x_accessory_total."""
        if raw_value in (None, '', False):
            return 0

        numeric_val = self._safe_int_from_text(raw_value)
        if numeric_val:
            return numeric_val

        parts = [p.strip() for p in str(raw_value).split(',') if p.strip()]
        return len(parts)

    def _resolve_category_id(self, product_type, group=None):
        """Resolve/create product category for imported product.

        Priority:
        1) product.group name as child category under product-type parent category
        2) fallback to product-type parent category
        """
        cat_model = self.env['product.category']
        parent_map = {
            'lens': ('Lens Products', '06'),
            'opt': ('Optical OPT', '27'),
            'accessory': ('Accessories', '20'),
        }
        parent_name, parent_code = parent_map.get(product_type, ('All Products', False))

        parent = cat_model.search([('name', '=', parent_name), ('parent_id', '=', False)], limit=1)
        if not parent:
            parent_vals = {'name': parent_name}
            if parent_code and 'code' in cat_model._fields:
                parent_vals['code'] = parent_code
            parent = cat_model.create(parent_vals)

        if group and group.name:
            child = cat_model.search([
                ('name', '=', group.name),
                ('parent_id', '=', parent.id),
            ], limit=1)
            if not child:
                child_vals = {
                    'name': group.name,
                    'parent_id': parent.id,
                }
                if parent_code and 'code' in cat_model._fields:
                    child_vals['code'] = parent_code
                child = cat_model.create(child_vals)
            return child.id

        return parent.id

    def _get_or_create_lens_power(self, power_type, raw_value):
        """Resolve product.lens.power by type/value, create when missing."""
        if raw_value in (None, '', False):
            return False

        value = self._safe_float_from_text(raw_value)
        power_model = self.env['product.lens.power']
        power = power_model.search([
            ('type', '=', power_type),
            ('value', '=', value),
        ], limit=1)
        if power:
            return power

        display = f"{value:+.2f}" if value >= 0 else f"{value:.2f}"
        return power_model.create({
            'name': display,
            'type': power_type,
            'value': value,
        })
    
    def _create_product(self, row_data, product_type, cache):
        product_vals = self._prepare_product_vals(row_data, product_type, cache)

        group = cache.get_group(row_data.get('Group'))
        brand = cache.get_brand(row_data.get('TradeMark'))
        
        # Generate abbreviation code automatically
        lens_index_id = False
        if product_type == 'lens' and row_data.get('Index'):
            index_record = cache.get_lens_index(row_data['Index'])
            if index_record:
                lens_index_id = index_record.id
        
        # Generate code if we have group and brand
        if group and brand:
            try:
                code = product_code_utils.generate_product_code(
                    self.env,
                    group.id,
                    brand.id,
                    lens_index_id
                )
                product_vals['default_code'] = code
                _logger.info(f"Generated code {code} for product {row_data.get('FullName')}")
            except Exception as e:
                _logger.warning(f"Could not generate code: {e}")
        
        # Create product
        product = self.env['product.template'].create(product_vals)
        self._upsert_supplierinfo(product, row_data, cache)
        
        return product
    
    def _prepare_lens_vals(self, row_data, cache):
        """Prepare lens_ids values"""
        lens_vals = {}

        # Power fields (Many2one to product.lens.power)
        sph_power = self._get_or_create_lens_power('sph', row_data.get('SPH'))
        if sph_power:
            lens_vals['sph_id'] = sph_power.id

        cyl_power = self._get_or_create_lens_power('cyl', row_data.get('CYL'))
        if cyl_power:
            lens_vals['cyl_id'] = cyl_power.id

        # Numeric fields
        if row_data.get('ADD') not in (None, '', False):
            lens_vals['lens_add'] = self._safe_float_from_text(row_data.get('ADD'))
        if row_data.get('AXIS') not in (None, '', False):
            lens_vals['axis'] = self._safe_int_from_text(row_data.get('AXIS'))
        if row_data.get('BASE') not in (None, '', False):
            lens_vals['base_curve'] = self._safe_float_from_text(row_data.get('BASE'))
        if row_data.get('Diameter') not in (None, '', False):
            lens_vals['diameter'] = self._safe_int_from_text(row_data.get('Diameter'))

        # Text fields (only fields that exist on product.lens)
        for excel_field, odoo_field in [
            ('PRISM', 'prism'),
            ('PRISMBASE', 'prism_base'),
            ('Abbe', 'abbe'),
            ('ColorInt', 'color_int'),
            ('Corridor', 'corridor'),
            ('MirCoating', 'mir_coating'),
        ]:
            if row_data.get(excel_field):
                lens_vals[odoo_field] = row_data[excel_field]
        
        # Foreign keys
        if row_data.get('Design1'):
            design = cache.get_design(row_data['Design1'])
            if design:
                lens_vals['design1_id'] = design.id
        
        if row_data.get('Design2'):
            design = cache.get_design(row_data['Design2'])
            if design:
                lens_vals['design2_id'] = design.id
        
        if row_data.get('Material'):
            material = cache.get_lens_material(row_data['Material'])
            if material:
                lens_vals['material_id'] = material.id
        
        if row_data.get('Index'):
            index = cache.get_lens_index(row_data['Index'])
            if index:
                lens_vals['index_id'] = index.id
        
        if row_data.get('Uv'):
            uv = cache.get_uv(row_data['Uv'])
            if uv:
                lens_vals['uv_id'] = uv.id
        
        if row_data.get('HMC'):
            hmc = cache.get_color(row_data['HMC'])
            if hmc:
                lens_vals['cl_hmc_id'] = hmc.id
        
        if row_data.get('PHO'):
            pho = cache.get_color(row_data['PHO'])
            if pho:
                lens_vals['cl_pho_id'] = pho.id
        
        if row_data.get('TIND'):
            tind = cache.get_color(row_data['TIND'])
            if tind:
                lens_vals['cl_tint_id'] = tind.id
        
        # Many2many: Coating (CSV)
        if row_data.get('Coating'):
            coating_ids = []
            for coating_cid in str(row_data['Coating']).split(','):
                coating = cache.get_coating(coating_cid.strip())
                if coating:
                    coating_ids.append(coating.id)
            if coating_ids:
                lens_vals['coating_ids'] = [(6, 0, coating_ids)]
        
        return lens_vals
    
    def _prepare_opt_vals(self, row_data, cache):
        """Prepare opt_ids values"""
        opt_vals = {}
        
        # Simple text fields
        for excel_field, odoo_field in [
            ('Sku', 'sku'), ('Model', 'model'), ('Model_Supplier', 'oem_ncc'),
            ('Serial', 'serial'), ('Season', 'season'),
        ]:
            if row_data.get(excel_field):
                opt_vals[odoo_field] = row_data[excel_field]
        
        # Gender
        if row_data.get('Gender'):
            opt_vals['gender'] = str(row_data['Gender'])
        
        # Dimensions
        for excel_field, odoo_field in [
            ('Lens_Width', 'lens_width'), ('Bridge_Width', 'bridge_width'),
            ('Temple_Width', 'temple_width'), ('Lens_Height', 'lens_height'),
            ('Lens_Span', 'lens_span'),
        ]:
            if row_data.get(excel_field):
                try:
                    opt_vals[odoo_field] = int(row_data[excel_field])
                except (ValueError, TypeError):
                    pass
        
        # Foreign keys
        fk_mapping = [
            ('Frame', 'frame_id', cache.get_frame),
            ('Frame_Type', 'frame_type_id', cache.get_frame_type),
            ('Shape', 'shape_id', cache.get_shape),
            ('Ve', 've_id', cache.get_ve),
            ('Temple', 'temple_id', cache.get_temple),
            ('Material_Ve', 'material_ve_id', cache.get_material),
            ('Material_TempleTip', 'material_temple_tip_id', cache.get_material),
            ('Material_Lens', 'material_lens_id', cache.get_material),
            ('Color_Lens', 'color_lens_id', cache.get_color),
            ('Color_Opt_Front', 'color_front_id', cache.get_color),
            ('Color_Opt_Temple', 'color_temple_id', cache.get_color),
        ]
        
        for excel_field, odoo_field, getter in fk_mapping:
            if row_data.get(excel_field):
                record = getter(row_data[excel_field])
                if record:
                    opt_vals[odoo_field] = record.id
        
        # Many2many: Materials (CSV)
        if row_data.get('Material_Opt_Front'):
            material_ids = []
            for mat_cid in str(row_data['Material_Opt_Front']).split(','):
                material = cache.get_material(mat_cid.strip())
                if material:
                    material_ids.append(material.id)
            if material_ids:
                opt_vals['materials_front_ids'] = [(6, 0, material_ids)]
        
        if row_data.get('Material_Opt_Temple'):
            material_ids = []
            for mat_cid in str(row_data['Material_Opt_Temple']).split(','):
                material = cache.get_material(mat_cid.strip())
                if material:
                    material_ids.append(material.id)
            if material_ids:
                opt_vals['materials_temple_ids'] = [(6, 0, material_ids)]
        
        # Many2many: Coating (CSV)
        if row_data.get('Coating'):
            coating_ids = []
            for coating_cid in str(row_data['Coating']).split(','):
                coating = cache.get_coating(coating_cid.strip())
                if coating:
                    coating_ids.append(coating.id)
            if coating_ids:
                opt_vals['coating_ids'] = [(6, 0, coating_ids)]
        
        return opt_vals

    def _prepare_opt_template_vals(self, row_data, cache):
        """Prepare template-level OPT fields (opt_*) used by current forms."""
        vals = {}

        text_map = [
            ('Sku', 'opt_sku'),
            ('Model', 'opt_model'),
            ('Model_Supplier', 'opt_oem_ncc'),
            ('Serial', 'opt_serial'),
            ('Season', 'opt_season'),
            ('Color_Code', 'opt_color'),
        ]
        for excel_field, odoo_field in text_map:
            if row_data.get(excel_field):
                vals[odoo_field] = row_data[excel_field]

        if row_data.get('Gender'):
            vals['opt_gender'] = str(row_data['Gender'])

        dim_map = [
            ('Lens_Width', 'opt_lens_width'),
            ('Bridge_Width', 'opt_bridge_width'),
            ('Temple_Width', 'opt_temple_width'),
            ('Lens_Height', 'opt_lens_height'),
            ('Lens_Span', 'opt_lens_span'),
        ]
        for excel_field, odoo_field in dim_map:
            if row_data.get(excel_field):
                vals[odoo_field] = self._safe_int_from_text(row_data[excel_field])

        fk_map = [
            ('Frame', 'opt_frame_id', cache.get_frame),
            ('Frame_Type', 'opt_frame_type_id', cache.get_frame_type),
            ('Shape', 'opt_shape_id', cache.get_shape),
            ('Ve', 'opt_ve_id', cache.get_ve),
            ('Temple', 'opt_temple_id', cache.get_temple),
            ('Material_Ve', 'opt_material_ve_id', cache.get_material),
            ('Material_TempleTip', 'opt_material_temple_tip_id', cache.get_material),
            ('Material_Lens', 'opt_material_lens_id', cache.get_material),
            ('Color_Lens', 'opt_color_lens_id', cache.get_color),
            ('Color_Opt_Front', 'opt_color_front_id', cache.get_color),
            ('Color_Opt_Temple', 'opt_color_temple_id', cache.get_color),
        ]
        for excel_field, odoo_field, getter in fk_map:
            if row_data.get(excel_field):
                record = getter(row_data[excel_field])
                if record:
                    vals[odoo_field] = record.id

        if vals.get('opt_color_front_id'):
            vals['opt_color_front_ids'] = [(6, 0, [vals['opt_color_front_id']])]
        if vals.get('opt_color_temple_id'):
            vals['opt_color_temple_ids'] = [(6, 0, [vals['opt_color_temple_id']])]

        if row_data.get('Material_Opt_Front'):
            material_ids = []
            for mat_code in str(row_data['Material_Opt_Front']).split(','):
                material = cache.get_material(mat_code.strip())
                if material:
                    material_ids.append(material.id)
            if material_ids:
                vals['opt_materials_front_ids'] = [(6, 0, material_ids)]

        if row_data.get('Material_Opt_Temple'):
            material_ids = []
            for mat_code in str(row_data['Material_Opt_Temple']).split(','):
                material = cache.get_material(mat_code.strip())
                if material:
                    material_ids.append(material.id)
            if material_ids:
                vals['opt_materials_temple_ids'] = [(6, 0, material_ids)]

        if row_data.get('Coating'):
            coating_ids = []
            for coating_code in str(row_data['Coating']).split(','):
                coating = cache.get_coating(coating_code.strip())
                if coating:
                    coating_ids.append(coating.id)
            if coating_ids:
                vals['opt_coating_ids'] = [(6, 0, coating_ids)]

        return vals

    def _prepare_lens_template_vals(self, row_data, cache, coating_ids=None):
        """Prepare template-level Lens fields (lens_* and x_*) used by current forms."""
        vals = {}

        sph_power = self._get_or_create_lens_power('sph', row_data.get('SPH'))
        cyl_power = self._get_or_create_lens_power('cyl', row_data.get('CYL'))
        add_power = self._get_or_create_lens_power('add', row_data.get('ADD'))

        vals.update({
            'x_sph': self._safe_float_from_text(row_data.get('SPH')),
            'x_cyl': self._safe_float_from_text(row_data.get('CYL')),
            'x_add': self._safe_float_from_text(row_data.get('ADD')),
            'x_axis': self._safe_int_from_text(row_data.get('AXIS')) if row_data.get('AXIS') not in (None, '', False) else False,
            'x_prism': row_data.get('PRISM') or '',
            'x_prism_base': row_data.get('PRISMBASE') or '',
            'x_mir_coating': row_data.get('MirCoating') or '',
            'x_diameter': self._safe_int_from_text(row_data.get('Diameter')),
            'lens_color_int': row_data.get('ColorInt') or '',
            'lens_base_curve': self._safe_float_from_text(row_data.get('BASE')),
            'lens_sph_id': sph_power.id if sph_power else False,
            'lens_cyl_id': cyl_power.id if cyl_power else False,
            'lens_add_id': add_power.id if add_power else False,
        })

        if row_data.get('Design1'):
            design_1 = cache.get_design(row_data.get('Design1'))
            vals['lens_design1_id'] = design_1.id if design_1 else False

        if row_data.get('Design2'):
            design_2 = cache.get_design(row_data.get('Design2'))
            vals['lens_design2_id'] = design_2.id if design_2 else False

        if row_data.get('Material'):
            material = cache.get_lens_material(row_data.get('Material'))
            vals['lens_material_id'] = material.id if material else False

        if row_data.get('Index'):
            index = cache.get_lens_index(row_data.get('Index'))
            vals['lens_index_id'] = index.id if index else False

        if row_data.get('Uv'):
            uv = cache.get_uv(row_data.get('Uv'))
            vals['lens_uv_id'] = uv.id if uv else False

        if row_data.get('HMC'):
            hmc = cache.get_color(row_data.get('HMC'))
            vals['lens_cl_hmc_id'] = hmc.id if hmc else False

        if row_data.get('PHO'):
            pho = cache.get_color(row_data.get('PHO'))
            vals['lens_cl_pho_id'] = pho.id if pho else False

        if row_data.get('TIND'):
            tint = cache.get_color(row_data.get('TIND'))
            vals['lens_cl_tint_id'] = tint.id if tint else False

        if coating_ids is None:
            coating_ids, _coating_codes = self._resolve_lens_coating_ids_from_row(row_data, cache)
        vals['lens_coating_ids'] = [(6, 0, coating_ids)] if coating_ids else False

        return vals

    def _prepare_accessory_template_vals(self, row_data, cache):
        """Prepare template-level Accessory fields."""
        vals = {}

        if row_data.get('Design'):
            design = cache.get_design(row_data['Design'])
            if design:
                vals['design_id'] = design.id

        if row_data.get('Shape'):
            shape = cache.get_shape(row_data['Shape'])
            if shape:
                vals['shape_id'] = shape.id

        if row_data.get('Material'):
            material = cache.get_material(row_data['Material'])
            if material:
                vals['material_id'] = material.id

        if row_data.get('Color'):
            color = cache.get_accessory_color(row_data['Color'])
            if color:
                vals['color_id'] = color.id

        numeric_map = [
            ('Width', 'acc_width'),
            ('Length', 'acc_length'),
            ('Height', 'acc_height'),
            ('Head', 'acc_head'),
            ('Body', 'acc_body'),
        ]
        for excel_field, odoo_field in numeric_map:
            if row_data.get(excel_field) not in (None, '', False):
                vals[odoo_field] = self._safe_float_from_text(row_data[excel_field])

        return vals
