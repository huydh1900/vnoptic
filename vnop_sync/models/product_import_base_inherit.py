# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import ValidationError


class ProductTemplateImportBaseInherit(models.Model):
    _inherit = 'product.template'

    _VNOP_LENS_M2O_FIELDS = ('lens_sph_id', 'lens_cyl_id', 'lens_add_id')

    _VNOP_EXPORT_TEMPLATE_PREFIX = 'VNOP - Product Template'

    _VNOP_COMMON_FIELDS = [
        'categ_id',
        'group_id',
        'image_1920',
        'name',
        'x_eng_name',
        'uom_id',
        'brand_id',
        'supplier_ref',
        'country_id',
        'default_code',
        'warranty_id',
        'warranty_supplier_id',
        'warranty_retail_id',
        'standard_price',
        'list_price',
        'x_ws_price',
        'x_ws_price_min',
        'x_ws_price_max',
        'x_uses',
        'x_guide',
        'x_warning',
        'x_preserve',
        'taxes_id',
        'supplier_taxes_id',
        'product_status',
    ]

    _VNOP_TYPE_FIELDS = {
        'lens': [
            'len_type',
            'lens_sph_id',
            'lens_cyl_id',
            'lens_add_id',
            'x_axis',
            'x_prism',
            'x_prism_base',
            'lens_base_curve',
            'x_diameter',
            'lens_design1_id',
            'lens_design2_id',
            'lens_material_id',
            'lens_index_id',
            'lens_uv_id',
            'lens_coating_ids',
            'lens_cl_hmc_id',
            'lens_cl_pho_id',
            'lens_cl_tint_id',
            'lens_color_int',
            'x_mir_coating',
        ],
        'frame': [
            'opt_sku',
            'opt_model',
            'opt_serial',
            'opt_color',
            'opt_season',
            'opt_gender',
            'opt_frame_id',
            'opt_frame_type_id',
            'opt_shape_id',
            'opt_ve_id',
            'opt_temple_id',
            'opt_material_ve_id',
            'opt_material_temple_tip_id',
            'opt_material_lens_id',
            'opt_materials_front_ids',
            'opt_materials_temple_ids',
            'opt_coating_ids',
            'opt_color_lens_id',
            'opt_color_front_ids',
            'opt_color_temple_ids',
            'opt_lens_width',
            'opt_bridge_width',
            'opt_temple_width',
            'opt_lens_height',
            'opt_lens_span',
        ],
        'accessory': [
            'design_id',
            'shape_id',
            'material_id',
            'color_id',
            'acc_width',
            'acc_length',
            'acc_height',
            'acc_head',
            'acc_body',
            'has_box',
            'has_cleaning_cloth',
            'has_warranty_card',
            'accessory_note',
        ],
    }

    _VNOP_REQUIRED_COMMON = [
        'name',
        'categ_id',
        'group_id',
        'uom_id',
        'brand_id',
        'country_id',
        'standard_price',
        'list_price',
        'product_status',
    ]

    _VNOP_REQUIRED_BY_TYPE = {
        'lens': [
            'len_type',
            'lens_sph_id',
            'lens_cyl_id',
            'lens_material_id',
            'lens_index_id',
        ],
        'frame': [
            'opt_sku',
            'opt_model',
            'opt_frame_type_id',
            'opt_shape_id',
        ],
        'accessory': [
            'design_id',
            'shape_id',
            'material_id',
            'color_id',
        ],
    }

    _VNOP_RELATIONAL_FIELDS = {
        'categ_id': {'multi': False},
        'group_id': {'multi': False},
        'uom_id': {'multi': False},
        'brand_id': {'multi': False},
        'country_id': {'multi': False},
        'warranty_id': {'multi': False},
        'warranty_supplier_id': {'multi': False},
        'warranty_retail_id': {'multi': False},
        'taxes_id': {'multi': True},
        'supplier_taxes_id': {'multi': True},
        'lens_sph_id': {'multi': False},
        'lens_cyl_id': {'multi': False},
        'lens_add_id': {'multi': False},
        'lens_design1_id': {'multi': False},
        'lens_design2_id': {'multi': False},
        'lens_material_id': {'multi': False},
        'lens_index_id': {'multi': False},
        'lens_uv_id': {'multi': False},
        'lens_coating_ids': {'multi': True},
        'lens_cl_hmc_id': {'multi': False},
        'lens_cl_pho_id': {'multi': False},
        'lens_cl_tint_id': {'multi': False},
        'opt_frame_id': {'multi': False},
        'opt_frame_type_id': {'multi': False},
        'opt_shape_id': {'multi': False},
        'opt_ve_id': {'multi': False},
        'opt_temple_id': {'multi': False},
        'opt_material_ve_id': {'multi': False},
        'opt_material_temple_tip_id': {'multi': False},
        'opt_material_lens_id': {'multi': False},
        'opt_materials_front_ids': {'multi': True},
        'opt_materials_temple_ids': {'multi': True},
        'opt_coating_ids': {'multi': True},
        'opt_color_lens_id': {'multi': False},
        'opt_color_front_ids': {'multi': True},
        'opt_color_temple_ids': {'multi': True},
        'design_id': {'multi': False},
        'shape_id': {'multi': False},
        'material_id': {'multi': False},
        'color_id': {'multi': False},
    }

    _VNOP_MODEL_SEARCH_KEYS = {
        'res.country': ['code', 'name'],
        'uom.uom': ['name'],
        'res.partner': ['ref', 'name'],
        'product.category': ['code', 'complete_name', 'name'],
        'product.lens.material': ['code', 'name'],
        'product.lens.index': ['cid', 'name'],
        'product.uv': ['cid', 'name'],
        'product.coating': ['cid', 'name'],
        'product.frame': ['cid', 'name'],
        'product.frame.type': ['cid', 'name'],
        'product.ve': ['cid', 'name'],
        'product.temple': ['cid', 'name'],
    }

    @api.model
    def _vnop_export_templates(self):
        return {
            'Mat': self._VNOP_COMMON_FIELDS + self._VNOP_TYPE_FIELDS['lens'],
            'Gong': self._VNOP_COMMON_FIELDS + self._VNOP_TYPE_FIELDS['frame'],
            'Phu kien': self._VNOP_COMMON_FIELDS + self._VNOP_TYPE_FIELDS['accessory'],
        }

    @api.model
    def _ensure_vnop_export_templates(self):
        Export = self.env['ir.exports'].sudo()
        Line = self.env['ir.exports.line'].sudo()

        for template_type, raw_fields in self._vnop_export_templates().items():
            template_name = f"{self._VNOP_EXPORT_TEMPLATE_PREFIX} - {template_type}"
            template_fields = [field for field in dict.fromkeys(raw_fields) if field in self._fields]
            export_rec = Export.search([
                ('resource', '=', 'product.template'),
                ('name', '=', template_name),
            ], limit=1)
            if not export_rec:
                export_rec = Export.create({
                    'name': template_name,
                    'resource': 'product.template',
                })

            current = export_rec.export_fields.mapped('name')
            if current == template_fields:
                continue

            export_rec.export_fields.unlink()
            Line.create([
                {'export_id': export_rec.id, 'name': field_name}
                for field_name in template_fields
            ])

        return True

    def _vnop_normalize_import_value(self, value):
        if value in (None, False):
            return ''
        text = str(value).strip()
        if not text:
            return ''
        if text.lower() in {'none', 'null', 'nan', 'n/a'}:
            return ''
        return text

    def _vnop_normalize_lens_power_token(self, token):
        """Normalize SPH/CYL/ADD token to lens power name format: +0.25, -0.50, 0.00."""
        text = self._vnop_normalize_import_value(token)
        if not text:
            return ''
        try:
            value = float(text)
            return '0.00' if value == 0 else f"{value:+.2f}"
        except (TypeError, ValueError):
            return text

    def _vnop_prepare_lens_dbid_fields(self, fields):
        """Use '.id' import path for lens SPH/CYL/ADD to bypass ambiguous name_search."""
        prepared = list(fields)
        for index, field_name in enumerate(prepared):
            if field_name in self._VNOP_LENS_M2O_FIELDS:
                prepared[index] = f'{field_name}/.id'
        return prepared

    def _vnop_get_search_keys(self, model_name):
        model = self.env[model_name]
        ordered_keys = self._VNOP_MODEL_SEARCH_KEYS.get(model_name, ['cid', 'code', 'default_code', 'name'])
        return [key for key in ordered_keys if key in model._fields]

    def _vnop_display_import_label(self, record):
        """Return stable label that Odoo import can resolve for many2one values."""
        if not record:
            return ''
        if record._name == 'product.category' and 'complete_name' in record._fields:
            return record.complete_name or record.display_name
        if 'name' in record._fields:
            return record.name
        return record.display_name

    def _vnop_pre_resolve_relational_cells(self, fields, rows):
        """Resolve relational tokens (code/cid/name) before delegating to Odoo import."""
        index_by_field = {field_name: index for index, field_name in enumerate(fields)}
        for row_no, row in enumerate(rows, start=1):
            for field_name in fields:
                if field_name not in self._VNOP_RELATIONAL_FIELDS or field_name not in index_by_field:
                    continue
                cell_value = row[index_by_field[field_name]]
                if not self._vnop_normalize_import_value(cell_value):
                    continue
                recs, normalized = self._vnop_resolve_reference(field_name, cell_value, row_no)
                if field_name in self._VNOP_LENS_M2O_FIELDS and recs:
                    row[index_by_field[field_name]] = str(recs.id)
                else:
                    row[index_by_field[field_name]] = normalized

    def _vnop_resolve_reference(self, field_name, raw_value, row_no):

        field = self._fields[field_name]
        model_name = field.comodel_name
        model = self.env[model_name].sudo()
        search_keys = self._vnop_get_search_keys(model_name)

        def _find_one(token):
            extra_domain = []
            if model_name == 'product.lens.power':
                if field_name == 'lens_sph_id':
                    extra_domain.append(('power_type', '=', 'sph'))
                elif field_name == 'lens_cyl_id':
                    extra_domain.append(('power_type', '=', 'cyl'))
                elif field_name == 'lens_add_id':
                    extra_domain.append(('power_type', '=', 'add'))
            for key in search_keys:
                domain = [(key, '=', token)] + extra_domain
                record = model.search(domain, limit=1)
                if record:
                    return record
            return model.browse()

        normalized = self._vnop_normalize_import_value(raw_value)
        if field_name in self._VNOP_LENS_M2O_FIELDS:
            normalized = self._vnop_normalize_lens_power_token(normalized)
        if not normalized:
            return model.browse(), ''

        if self._VNOP_RELATIONAL_FIELDS[field_name]['multi']:
            records = model.browse()
            labels = []
            for item in [x.strip() for x in normalized.split(',') if self._vnop_normalize_import_value(x)]:
                rec = _find_one(item)
                if not rec:
                    raise ValidationError(_(
                        'Dòng %(row)s: Không tìm thấy giá trị "%(value)s" cho cột %(field)s.',
                        row=row_no,
                        value=item,
                        field=field.string,
                    ))
                records |= rec
                labels.append(self._vnop_display_import_label(rec))
            return records, ','.join(labels)

        rec = _find_one(normalized)
        if not rec:
            raise ValidationError(_(
                'Dòng %(row)s: Không tìm thấy giá trị "%(value)s" cho cột %(field)s.',
                row=row_no,
                value=normalized,
                field=field.string,
            ))
        return rec, self._vnop_display_import_label(rec)

    def _vnop_guess_import_type(self, fields):
        markers = {
            'lens': {'len_type', 'lens_sph_id', 'lens_cyl_id', 'lens_index_id'},
            'frame': {'opt_sku', 'opt_model', 'opt_frame_type_id', 'opt_shape_id'},
            'accessory': {'design_id', 'shape_id', 'material_id', 'color_id'},
        }
        fields_set = set(fields)
        scored = {
            product_type: len(fields_set.intersection(product_fields))
            for product_type, product_fields in markers.items()
        }
        best_type = max(scored, key=scored.get)
        return best_type if scored[best_type] > 0 else False

    def _vnop_product_type_from_record(self, record):
        code = (record.categ_code or '').strip().upper()
        if code == 'TK':
            return 'lens'
        if code == 'GK':
            return 'frame'
        if code in ('PK', 'TB', 'LK'):
            return 'accessory'
        return False

    @api.model
    def load(self, fields, data):
        if not self.env.context.get('import_file'):
            return super().load(fields, data)
        if not fields:
            return super().load(fields, data)

        # Allow imports that only update relational fields (e.g. categ_id by code)
        # even when default_code is not included in the file.
        if 'default_code' not in fields:
            fields = list(fields)
            rows = [list(row) for row in data]
            # Bỏ supplier_ref (virtual column) trước khi load
            if 'supplier_ref' in fields:
                sup_idx = fields.index('supplier_ref')
                fields.pop(sup_idx)
                for row in rows:
                    row.pop(sup_idx)
            self._vnop_validate_unique_names(fields, rows)
            self._vnop_pre_resolve_relational_cells(list(fields), rows)
            prepared_fields = self._vnop_prepare_lens_dbid_fields(fields)
            return super().load(prepared_fields, rows)

        import_type = self._vnop_guess_import_type(fields)
        if not import_type:
            return super().load(fields, data)

        fields = list(fields)
        rows = [list(row) for row in data]
        index_by_field = {field_name: index for index, field_name in enumerate(fields)}
        code_index = index_by_field['default_code']

        required_fields = [
            field_name
            for field_name in (self._VNOP_REQUIRED_COMMON + self._VNOP_REQUIRED_BY_TYPE[import_type])
            if field_name in index_by_field
        ]

        required_columns = [
            field_name
            for field_name in (self._VNOP_REQUIRED_COMMON + self._VNOP_REQUIRED_BY_TYPE[import_type])
            if field_name in self._fields
        ]
        missing_columns = [
            self._fields[field_name].string
            for field_name in required_columns
            if field_name not in index_by_field
        ]
        if missing_columns:
            raise ValidationError(_(
                'Thiếu cột bắt buộc trong file import (%(type)s): %(columns)s',
                type=import_type,
                columns=', '.join(missing_columns),
            ))

        file_codes = set()
        existing_by_code = {}
        locked_relational_values = defaultdict(dict)

        for row_no, row in enumerate(rows, start=1):
            code = self._vnop_normalize_import_value(row[code_index] if code_index < len(row) else '')
            if code:
                if code in file_codes:
                    raise ValidationError(_('Dòng %s: Trùng mã sản phẩm trong cùng file (%s).') % (row_no, code))
                file_codes.add(code)

            for field_name in required_fields:
                value = self._vnop_normalize_import_value(row[index_by_field[field_name]])
                if not value:
                    raise ValidationError(_(
                        'Dòng %(row)s: Thiếu trường bắt buộc %(field)s.',
                        row=row_no,
                        field=self._fields[field_name].string,
                    ))

            for field_name in fields:
                if field_name not in self._VNOP_RELATIONAL_FIELDS or field_name not in index_by_field:
                    continue
                cell_value = row[index_by_field[field_name]]
                if not self._vnop_normalize_import_value(cell_value):
                    continue
                recs, normalized = self._vnop_resolve_reference(field_name, cell_value, row_no)
                if field_name in self._VNOP_LENS_M2O_FIELDS and recs:
                    row[index_by_field[field_name]] = str(recs.id)
                else:
                    row[index_by_field[field_name]] = normalized
                if recs and not self._VNOP_RELATIONAL_FIELDS[field_name]['multi']:
                    locked_relational_values[row_no][field_name] = recs.id

            if code:
                existing = self.search([('default_code', '=', code)], limit=1)
                if existing:
                    existing_by_code[code] = existing
                    existing_type = self._vnop_product_type_from_record(existing)
                    if existing_type and existing_type != import_type:
                        raise ValidationError(_(
                            'Dòng %(row)s: Mã %(code)s đã tồn tại nhưng khác loại sản phẩm.',
                            row=row_no,
                            code=code,
                        ))

                    if 'categ_id' in index_by_field and locked_relational_values[row_no].get('categ_id'):
                        if existing.categ_id.id != locked_relational_values[row_no]['categ_id']:
                            raise ValidationError(_(
                                'Dòng %(row)s: Mã %(code)s đã tồn tại nhưng đang thay đổi Danh mục.',
                                row=row_no,
                                code=code,
                            ))

                    if 'group_id' in index_by_field and locked_relational_values[row_no].get('group_id'):
                        if existing.group_id.id != locked_relational_values[row_no]['group_id']:
                            raise ValidationError(_(
                                'Dòng %(row)s: Mã %(code)s đã tồn tại nhưng đang thay đổi Nhóm sản phẩm.',
                                row=row_no,
                                code=code,
                            ))

        if '.id' not in fields and 'id' not in fields:
            fields.insert(0, '.id')
            for row in rows:
                code = self._vnop_normalize_import_value(row[code_index])
                existing = existing_by_code.get(code)
                row.insert(0, str(existing.id) if existing else '')

        # Extract supplier_ref (virtual column) trước khi gọi super
        supplier_data = {}
        if 'supplier_ref' in fields:
            sup_idx = fields.index('supplier_ref')
            for row_no, row in enumerate(rows):
                raw = self._vnop_normalize_import_value(row[sup_idx])
                if raw:
                    # Giá trị dạng "tên NCC - ref" → chỉ lấy ref
                    ref = raw.rsplit(' - ', 1)[-1].strip() if ' - ' in raw else raw.strip()
                    supplier_data[row_no] = ref
            # Bỏ cột supplier_ref ra khỏi fields/data
            fields.pop(sup_idx)
            for row in rows:
                row.pop(sup_idx)
            # Cập nhật code_index nếu bị dịch
            if sup_idx <= code_index:
                code_index -= 1

        prepared_fields = self._vnop_prepare_lens_dbid_fields(fields)
        result = super().load(prepared_fields, rows)

        # Sau import, tạo product.supplierinfo cho supplier_ref
        imported_ids = result.get('ids') or []
        if supplier_data and imported_ids:
            SupplierInfo = self.env['product.supplierinfo'].sudo()
            Partner = self.env['res.partner'].sudo()
            ref_cache = {}
            for row_no, ref in supplier_data.items():
                if row_no >= len(imported_ids):
                    continue
                product_id = imported_ids[row_no]
                if not product_id:
                    continue
                if ref not in ref_cache:
                    partner = Partner.search([('ref', '=', ref), ('supplier_rank', '>', 0)], limit=1)
                    ref_cache[ref] = partner.id if partner else False
                partner_id = ref_cache[ref]
                if not partner_id:
                    continue
                product = self.browse(product_id)
                if not product.seller_ids.filtered(lambda s: s.partner_id.id == partner_id):
                    SupplierInfo.create({
                        'product_tmpl_id': product_id,
                        'partner_id': partner_id,
                    })

        return result

    def _vnop_validate_unique_names(self, fields, rows):
        """Kiểm tra trùng tên sản phẩm trong file và trong DB."""
        if 'name' not in fields:
            return
        name_idx = list(fields).index('name')

        # Check trùng name trong file
        seen = {}
        for row_no, row in enumerate(rows, start=1):
            name = self._vnop_normalize_import_value(
                row[name_idx] if name_idx < len(row) else '')
            if not name:
                continue
            if name in seen:
                raise ValidationError(_(
                    'Dòng %(row)s: Trùng tên sản phẩm "%(name)s" với dòng %(first)s trong cùng file.',
                    row=row_no, name=name, first=seen[name],
                ))
            seen[name] = row_no

        # Check name đã tồn tại trong DB
        unique_names = list(seen.keys())
        if not unique_names:
            return
        existing = self.with_context(active_test=False).search_read(
            [('name', 'in', unique_names)],
            ['name'],
        )
        existing_map = {r['name']: r['name'] for r in existing if r['name']}
        for row_no, row in enumerate(rows, start=1):
            name = self._vnop_normalize_import_value(
                row[name_idx] if name_idx < len(row) else '')
            if name and name in existing_map:
                raise ValidationError(_(
                    'Dòng %(row)s: Tên sản phẩm "%(name)s" đã tồn tại trong hệ thống.',
                    row=row_no, name=name,
                ))
