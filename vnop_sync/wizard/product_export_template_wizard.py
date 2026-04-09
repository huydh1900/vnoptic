import base64
from io import BytesIO

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError


class ProductExportTemplateWizard(models.TransientModel):
    _name = 'product.export.template.wizard'
    _description = 'Export Product Template Wizard'

    _COMPANY_TITLE = 'CÔNG TY TNHH CÔNG NGHỆ QUANG HỌC VIỆT NAM'
    _COMPANY_ADDRESS = 'Số 63 phố Lê Duẩn, Phường Cửa Nam, Quận Hoàn Kiếm, Thành phố Hà Nội, Việt Nam'

    _TYPE_CONFIG = {
        'lens': {
            'template_key': 'Mat',
            'file_key': 'mat',
            'display_name': 'Mắt kính',
            'group_types': ['DT', 'HT', 'PT', 'DAT'],
        },
        'frame': {
            'template_key': 'Gong',
            'file_key': 'gong',
            'display_name': 'Gọng kính',
            'group_types': ['GK'],
        },
        'accessory': {
            'template_key': 'Phu kien',
            'file_key': 'phu_kien',
            'display_name': 'Phụ kiện',
            'group_types': ['PK', 'TB', 'LK'],
        },
    }

    _FIELD_LABEL_OVERRIDES = {
        'default_code': 'Mã sản phẩm',
        'image_1920': 'Hình ảnh',
        'name': 'Tên đầy đủ',
        'x_eng_name': 'Tên tiếng Anh',
        'categ_id': 'Danh mục (GK/TK/PK)',
        'group_id': 'Phân nhóm phụ',
        'uom_id': 'Đơn vị tính',
        'brand_id': 'Thương hiệu',
        'country_id': 'Xuất xứ',
        'warranty_id': 'Bảo hành hãng',
        'warranty_supplier_id': 'Bảo hành công ty',
        'warranty_retail_id': 'Bảo hành bán lẻ',
        'standard_price': 'Giá vốn',
        'list_price': 'Giá bán',
        'x_ws_price': 'Giá sỉ',
        'x_ws_price_min': 'Giá sỉ tối thiểu',
        'x_ws_price_max': 'Giá sỉ tối đa',
        'x_uses': 'Công dụng',
        'x_guide': 'Hướng dẫn sử dụng',
        'x_warning': 'Cảnh báo',
        'x_preserve': 'Bảo quản',
        'description': 'Mô tả',
        'taxes_id': 'Thuế bán',
        'supplier_taxes_id': 'Thuế mua',
        'product_status': 'Trạng thái',
    }

    # Mapping: real field name → display code trong Excel template
    # Trường nào là field trực tiếp trên product.template thì giữ nguyên,
    # trường nào tham chiếu model khác thì đổi sang code/cid/name tương ứng.
    _FIELD_CODE_OVERRIDES = {
        # Common
        'categ_id': 'categ_code',
        'group_id': 'group_cid',
        'uom_id': 'uom_name',
        'brand_id': 'brand_code',
        'country_id': 'country_code',
        'warranty_id': 'warranty_code',
        'warranty_supplier_id': 'warranty_supplier_code',
        'warranty_retail_id': 'warranty_retail_code',
        'taxes_id': 'taxes',
        'supplier_taxes_id': 'supplier_taxes',
        # Lens
        'lens_sph_id': 'lens_sph',
        'lens_cyl_id': 'lens_cyl',
        'lens_add_id': 'lens_add',
        'lens_design1_id': 'lens_design1_cid',
        'lens_design2_id': 'lens_design2_cid',
        'lens_material_id': 'lens_material_code',
        'lens_index_id': 'lens_index_cid',
        'lens_uv_id': 'lens_uv_cid',
        'lens_coating_ids': 'lens_coating_cid',
        'lens_cl_hmc_id': 'lens_cl_hmc_cid',
        'lens_cl_pho_id': 'lens_cl_pho_cid',
        'lens_cl_tint_id': 'lens_cl_tint_cid',
        # Frame
        'opt_frame_id': 'opt_frame_cid',
        'opt_frame_type_id': 'opt_frame_type_cid',
        'opt_shape_id': 'opt_shape_cid',
        'opt_ve_id': 'opt_ve_cid',
        'opt_temple_id': 'opt_temple_cid',
        'opt_material_ve_id': 'opt_material_ve_cid',
        'opt_material_temple_tip_id': 'opt_material_temple_tip_cid',
        'opt_material_lens_id': 'opt_material_lens_cid',
        'opt_materials_front_ids': 'opt_materials_front_cid',
        'opt_materials_temple_ids': 'opt_materials_temple_cid',
        'opt_coating_ids': 'opt_coating_cid',
        'opt_color_lens_id': 'opt_color_lens_cid',
        'opt_color_front_ids': 'opt_color_front_cid',
        'opt_color_temple_ids': 'opt_color_temple_cid',
        # Accessory
        'design_id': 'design_cid',
        'shape_id': 'shape_cid',
        'material_id': 'material_cid',
        'color_id': 'color_cid',
    }

    _VIRTUAL_IMPORT_COLUMNS = [
        'supplier_ref',
        'currency_id',
    ]

    _VIRTUAL_FIELD_LABELS = {
        'supplier_ref': 'Nhà cung cấp (ref)',
        'currency_id': 'Đơn vị nguyên tệ',
    }

    product_type = fields.Selection([
        ('lens', 'Mắt kính'),
        ('frame', 'Gọng kính'),
        ('accessory', 'Phụ kiện'),
    ], string='Loại sản phẩm', required=True)

    @api.model
    def _get_template_payload(self, product_type):
        config = self._TYPE_CONFIG.get(product_type)
        if not config:
            raise UserError('Loại sản phẩm không hợp lệ.')

        product_model = self.env['product.template']
        templates = product_model._vnop_export_templates()
        fields_list = templates.get(config['template_key']) or []
        fields_list = self._prepare_fields_for_export(product_model, fields_list)
        if not fields_list:
            raise UserError('Không tìm thấy danh sách cột cho template đã chọn.')

        content = self._build_xlsx_template(product_model, fields_list, product_type=product_type)
        return {
            'content': content,
            'filename': f"Bảng_mẫu_import_{config['file_key']}.xlsx",
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }

    def _prepare_fields_for_export(self, product_model, raw_fields):
        fields_list = []
        seen = set()
        virtual_set = set(self._VIRTUAL_IMPORT_COLUMNS)

        for field_name in raw_fields:
            if field_name not in seen and (
                field_name in product_model._fields or field_name in virtual_set
            ):
                fields_list.append(field_name)
                seen.add(field_name)

        # New templates should not expose default_code for manual input.
        if 'default_code' in seen:
            fields_list = [field_name for field_name in fields_list if field_name != 'default_code']
            seen.remove('default_code')

        if 'description' in product_model._fields:
            fields_list = [name for name in fields_list if name != 'description']
            fields_list.append('description')

        return fields_list

    def _label_for_field(self, product_model, field_name):
        if field_name in self._FIELD_LABEL_OVERRIDES:
            return self._FIELD_LABEL_OVERRIDES[field_name]
        if field_name in self._VIRTUAL_FIELD_LABELS:
            return self._VIRTUAL_FIELD_LABELS[field_name]
        field = product_model._fields[field_name]
        return field.string or field_name


    def _build_xlsx_template(self, product_model, fields_list, product_type=None):
        stream = BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})

        sheet = workbook.add_worksheet('Mẫu_nhập_liệu')

        last_col = max(0, len(fields_list) - 1)
        font_name = 'Times New Roman'
        font_size = 14

        title_style = workbook.add_format({
            'bold': True,
            'font_name': font_name,
            'font_size': 18,
            'align': 'left',
            'valign': 'vcenter',
        })
        subtitle_style = workbook.add_format({
            'italic': True,
            'font_name': font_name,
            'font_size': font_size,
            'align': 'left',
            'valign': 'vcenter',
        })
        header_style = workbook.add_format({
            'bold': True,
            'font_name': font_name,
            'font_size': font_size,
            'border': 1,
            'text_wrap': True,
            'align': 'center',
            'valign': 'vcenter',
        })
        code_style = workbook.add_format({
            'font_name': font_name,
            'font_size': font_size,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })

        # Row 0: company title, Row 1: address, Row 2: spacer
        sheet.merge_range(0, 0, 0, last_col, self._COMPANY_TITLE, title_style)
        sheet.merge_range(1, 0, 1, last_col, self._COMPANY_ADDRESS, subtitle_style)
        sheet.set_row(0, 28)
        sheet.set_row(1, 20)
        sheet.set_row(2, 8)
        # Row 3: header labels, Row 4: field codes
        sheet.set_row(3, 30)
        sheet.set_row(4, 24)

        # Excel column width unit ~ 1 character at default font (Calibri 11).
        # Times New Roman 14 is ~1.4x wider, so scale accordingly.
        width_scale = 1.4

        for col, field_name in enumerate(fields_list):
            label = self._label_for_field(product_model, field_name)
            display_code = self._FIELD_CODE_OVERRIDES.get(field_name, field_name)

            sheet.write(3, col, label, header_style)
            sheet.write(4, col, display_code, code_style)

            char_width = max(len(label), len(display_code))
            col_width = char_width * width_scale + 2
            sheet.set_column(col, col, col_width)

        # Data validation: cột categ_id chỉ cho chọn đúng loại theo product_type
        categ_map = {'lens': 'TK', 'frame': 'GK', 'accessory': 'PK'}
        if 'categ_id' in fields_list and product_type in categ_map:
            categ_col = fields_list.index('categ_id')
            allowed_categ = categ_map[product_type]
            sheet.data_validation(5, categ_col, 1048575, categ_col, {
                'validate': 'list',
                'source': [allowed_categ],
                'error_title': 'Giá trị không hợp lệ',
                'error_message': f'Danh mục chỉ chấp nhận: {allowed_categ}.',
            })

        # Data validation: cột uom_id chỉ cho chọn Chiếc
        if 'uom_id' in fields_list:
            uom_col = fields_list.index('uom_id')
            sheet.data_validation(5, uom_col, 1048575, uom_col, {
                'validate': 'list',
                'source': ['Chiếc'],
                'error_title': 'Giá trị không hợp lệ',
                'error_message': 'Đơn vị tính chỉ chấp nhận: Chiếc.',
            })

        # Data validation: cột group_id chỉ cho chọn CID theo product_type
        if 'group_id' in fields_list and product_type:
            config = self._TYPE_CONFIG.get(product_type)
            group_types = config.get('group_types', []) if config else []
            if group_types:
                groups = self.env['product.group'].search(
                    [('product_type', 'in', group_types)],
                    order='sequence',
                )
                group_cids = groups.mapped('cid')
                if group_cids:
                    group_col = fields_list.index('group_id')
                    sheet.data_validation(5, group_col, 1048575, group_col, {
                        'validate': 'list',
                        'source': group_cids,
                        'error_title': 'Giá trị không hợp lệ',
                        'error_message': 'Phân nhóm phụ không thuộc danh mục đã chọn.',
                    })

        # Data validation: cột brand_id chỉ cho chọn code từ product.brand
        if 'brand_id' in fields_list:
            brands = self.env['product.brand'].search([], order='sequence')
            brand_codes = [c for c in brands.mapped('code') if c]
            if brand_codes:
                brand_col = fields_list.index('brand_id')
                sheet.data_validation(5, brand_col, 1048575, brand_col, {
                    'validate': 'list',
                    'source': brand_codes,
                    'error_title': 'Giá trị không hợp lệ',
                    'error_message': 'Thương hiệu không hợp lệ.',
                })

        # Data validation: cột supplier_ref hiển thị "tên - ref", import chỉ lấy ref
        if 'supplier_ref' in fields_list:
            suppliers = self.env['res.partner'].search(
                [('supplier_rank', '>', 0), ('ref', '!=', False)],
                order='name',
            )
            supplier_labels = [f'{s.name} - {s.ref}' for s in suppliers if s.ref]
            if supplier_labels:
                ref_sheet = workbook.add_worksheet('_ref_suppliers')
                ref_sheet.hide()
                for row_idx, label in enumerate(supplier_labels):
                    ref_sheet.write(row_idx, 0, label)
                supplier_col = fields_list.index('supplier_ref')
                sheet.data_validation(5, supplier_col, 1048575, supplier_col, {
                    'validate': 'list',
                    'source': f'=_ref_suppliers!$A$1:$A${len(supplier_labels)}',
                    'error_title': 'Giá trị không hợp lệ',
                    'error_message': 'Nhà cung cấp không hợp lệ.',
                })

        # Data validation: cột country_id lấy code từ res.country
        if 'country_id' in fields_list:
            countries = self.env['res.country'].search([], order='name')
            country_codes = [c for c in countries.mapped('code') if c]
            if country_codes:
                ref_sheet_countries = workbook.add_worksheet('_ref_countries')
                ref_sheet_countries.hide()
                for row_idx, code in enumerate(country_codes):
                    ref_sheet_countries.write(row_idx, 0, code)
                country_col = fields_list.index('country_id')
                sheet.data_validation(5, country_col, 1048575, country_col, {
                    'validate': 'list',
                    'source': f'=_ref_countries!$A$1:$A${len(country_codes)}',
                    'error_title': 'Giá trị không hợp lệ',
                    'error_message': 'Mã quốc gia không hợp lệ.',
                })

        # Data validation: cột bảo hành lấy code từ product.warranty
        warranty_fields = ['warranty_id', 'warranty_supplier_id', 'warranty_retail_id']
        warranty_in_template = [f for f in warranty_fields if f in fields_list]
        if warranty_in_template:
            warranties = self.env['product.warranty'].search([], order='code')
            warranty_codes = [c for c in warranties.mapped('code') if c]
            if warranty_codes:
                for field_name in warranty_in_template:
                    col = fields_list.index(field_name)
                    sheet.data_validation(5, col, 1048575, col, {
                        'validate': 'list',
                        'source': warranty_codes,
                        'error_title': 'Giá trị không hợp lệ',
                        'error_message': 'Mã bảo hành không hợp lệ.',
                    })

        # Data validation: Selection fields
        selection_validations = {
            'product_status': ['new', 'current'],
            'len_type': ['DT', 'HT', 'DAT', 'PT'],
            'opt_gender': ['0', '1', '2', '3'],
            'has_box': ['TRUE', 'FALSE'],
            'has_cleaning_cloth': ['TRUE', 'FALSE'],
            'has_warranty_card': ['TRUE', 'FALSE'],
        }
        for field_name, values in selection_validations.items():
            if field_name in fields_list:
                col = fields_list.index(field_name)
                sheet.data_validation(5, col, 1048575, col, {
                    'validate': 'list',
                    'source': values,
                    'error_title': 'Giá trị không hợp lệ',
                    'error_message': f'Giá trị chỉ chấp nhận: {", ".join(values)}.',
                })

        # Data validation: Many2one fields lấy code/name từ model
        # Dùng hidden sheet vì danh sách có thể dài (SPH/CYL có nhiều giá trị)
        m2o_validations = {
            'lens_sph_id': {
                'model': 'product.lens.power',
                'domain': [('power_type', '=', 'sph')],
                'field': 'name',
                'order': 'value',
                'sheet': '_ref_sph',
                'error': 'Giá trị SPH không hợp lệ.',
            },
            'lens_cyl_id': {
                'model': 'product.lens.power',
                'domain': [('power_type', '=', 'cyl')],
                'field': 'name',
                'order': 'value',
                'sheet': '_ref_cyl',
                'error': 'Giá trị CYL không hợp lệ.',
            },
            'lens_add_id': {
                'model': 'product.lens.add',
                'domain': [],
                'field': 'name',
                'order': 'value',
                'sheet': '_ref_add',
                'error': 'Giá trị ADD không hợp lệ.',
            },
            'lens_design1_id': {
                'model': 'product.design',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_design',
                'error': 'Mã thiết kế không hợp lệ.',
            },
            'lens_design2_id': {
                'model': 'product.design',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_design2',
                'error': 'Mã thiết kế không hợp lệ.',
            },
            'lens_material_id': {
                'model': 'product.lens.material',
                'domain': [],
                'field': 'code',
                'order': 'name',
                'sheet': '_ref_material',
                'error': 'Mã vật liệu không hợp lệ.',
            },
            'lens_index_id': {
                'model': 'product.lens.index',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_index',
                'error': 'Mã chiết suất không hợp lệ.',
            },
            'lens_uv_id': {
                'model': 'product.uv',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_uv',
                'error': 'Mã UV không hợp lệ.',
            },
            'lens_cl_hmc_id': {
                'model': 'product.cl',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_hmc',
                'error': 'Mã HMC không hợp lệ.',
            },
            'lens_cl_pho_id': {
                'model': 'product.cl',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_pho',
                'error': 'Mã Photochromic không hợp lệ.',
            },
            'lens_cl_tint_id': {
                'model': 'product.cl',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_tint',
                'error': 'Mã Tinted không hợp lệ.',
            },
            # ── Gọng kính ──
            'opt_frame_id': {
                'model': 'product.frame',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_frame',
                'error': 'Mã gọng không hợp lệ.',
            },
            'opt_frame_type_id': {
                'model': 'product.frame.type',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_frame_type',
                'error': 'Mã loại gọng không hợp lệ.',
            },
            'opt_shape_id': {
                'model': 'product.shape',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_shape',
                'error': 'Mã hình dáng không hợp lệ.',
            },
            'opt_ve_id': {
                'model': 'product.ve',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_ve',
                'error': 'Mã ve không hợp lệ.',
            },
            'opt_temple_id': {
                'model': 'product.temple',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_temple',
                'error': 'Mã càng kính không hợp lệ.',
            },
            'opt_material_ve_id': {
                'model': 'product.material',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_mat',
                'error': 'Mã chất liệu không hợp lệ.',
            },
            'opt_material_temple_tip_id': {
                'model': 'product.material',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_mat_tip',
                'error': 'Mã chất liệu không hợp lệ.',
            },
            'opt_material_lens_id': {
                'model': 'product.material',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_mat_lens',
                'error': 'Mã chất liệu không hợp lệ.',
            },
            'opt_color_lens_id': {
                'model': 'product.cl',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_cl_lens',
                'error': 'Mã màu không hợp lệ.',
            },
            # ── Phụ kiện ──
            'design_id': {
                'model': 'product.design',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_acc_design',
                'error': 'Mã thiết kế không hợp lệ.',
            },
            'shape_id': {
                'model': 'product.shape',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_acc_shape',
                'error': 'Mã hình dáng không hợp lệ.',
            },
            'material_id': {
                'model': 'product.material',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_acc_mat',
                'error': 'Mã chất liệu không hợp lệ.',
            },
            'color_id': {
                'model': 'product.color',
                'domain': [],
                'field': 'cid',
                'order': 'name',
                'sheet': '_ref_acc_color',
                'error': 'Mã màu không hợp lệ.',
            },
        }
        # Cache: tránh tạo trùng hidden sheet cho cùng model+domain+field
        _ref_sheet_cache = {}
        for field_name, cfg in m2o_validations.items():
            if field_name not in fields_list:
                continue
            cache_key = (cfg['model'], tuple(cfg['domain']), cfg['field'])
            if cache_key in _ref_sheet_cache:
                ref_source = _ref_sheet_cache[cache_key]
            else:
                records = self.env[cfg['model']].search(cfg['domain'], order=cfg['order'])
                values = [v for v in records.mapped(cfg['field']) if v]
                if not values:
                    continue
                ref_ws = workbook.add_worksheet(cfg['sheet'])
                ref_ws.hide()
                for idx, val in enumerate(values):
                    ref_ws.write(idx, 0, val)
                ref_source = f"={cfg['sheet']}!$A$1:$A${len(values)}"
                _ref_sheet_cache[cache_key] = ref_source

            col = fields_list.index(field_name)
            sheet.data_validation(5, col, 1048575, col, {
                'validate': 'list',
                'source': ref_source,
                'error_title': 'Giá trị không hợp lệ',
                'error_message': cfg['error'],
            })

        # Data validation: Many2many fields lấy code từ model
        m2m_validations = {
            'lens_coating_ids': {
                'model': 'product.coating',
                'field': 'cid',
                'sheet': '_ref_coating',
                'error': 'Mã lớp phủ không hợp lệ.',
            },
            'opt_materials_front_ids': {
                'model': 'product.material',
                'field': 'cid',
                'sheet': '_ref_mat_front',
                'error': 'Mã chất liệu không hợp lệ.',
            },
            'opt_materials_temple_ids': {
                'model': 'product.material',
                'field': 'cid',
                'sheet': '_ref_mat_temple',
                'error': 'Mã chất liệu không hợp lệ.',
            },
            'opt_coating_ids': {
                'model': 'product.coating',
                'field': 'cid',
                'sheet': '_ref_opt_coating',
                'error': 'Mã lớp phủ không hợp lệ.',
            },
            'opt_color_front_ids': {
                'model': 'product.cl',
                'field': 'cid',
                'sheet': '_ref_cl_front',
                'error': 'Mã màu không hợp lệ.',
            },
            'opt_color_temple_ids': {
                'model': 'product.cl',
                'field': 'cid',
                'sheet': '_ref_cl_temple',
                'error': 'Mã màu không hợp lệ.',
            },
        }
        _m2m_sheet_cache = {}
        for field_name, cfg in m2m_validations.items():
            if field_name not in fields_list:
                continue
            cache_key = (cfg['model'], cfg['field'])
            if cache_key in _m2m_sheet_cache:
                ref_source = _m2m_sheet_cache[cache_key]
            else:
                records = self.env[cfg['model']].search([], order='name')
                values = [v for v in records.mapped(cfg['field']) if v]
                if not values:
                    continue
                ref_ws = workbook.add_worksheet(cfg['sheet'])
                ref_ws.hide()
                for idx, val in enumerate(values):
                    ref_ws.write(idx, 0, val)
                ref_source = f"={cfg['sheet']}!$A$1:$A${len(values)}"
                _m2m_sheet_cache[cache_key] = ref_source
            col = fields_list.index(field_name)
            sheet.data_validation(5, col, 1048575, col, {
                'validate': 'list',
                'source': ref_source,
                'error_title': 'Giá trị không hợp lệ',
                'error_message': cfg['error'],
            })

        sheet.freeze_panes(5, 0)

        workbook.close()
        return stream.getvalue()

    def action_export_template(self):
        self.ensure_one()
        payload = self._get_template_payload(self.product_type)
        attachment = self.env['ir.attachment'].create({
            'name': payload['filename'],
            'type': 'binary',
            'datas': base64.b64encode(payload['content']),
            'mimetype': payload['mimetype'],
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }
