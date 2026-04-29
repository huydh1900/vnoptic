# -*- coding: utf-8 -*-
import base64
import io
import logging

from openpyxl import load_workbook

from odoo import fields, models, _
from odoo.exceptions import UserError

from .product_export_template_wizard import ProductExportTemplateWizard

_logger = logging.getLogger(__name__)

PRODUCT_TYPE_SELECTION = [
    ('lens', 'Mắt kính'),
    ('frame', 'Gọng kính'),
    ('accessory', 'Phụ kiện'),
]


class ProductImportWizard(models.TransientModel):
    _name = 'product.import.wizard'
    _description = 'Import sản phẩm từ Excel'

    product_type = fields.Selection(
        selection=PRODUCT_TYPE_SELECTION,
        string='Loại sản phẩm',
        required=True,
        default='lens',
    )
    file_data = fields.Binary(string='File Excel', required=True)
    file_name = fields.Char()

    # Results
    state = fields.Selection([
        ('upload', 'Upload'),
        ('preview', 'Kiểm thử'),
        ('done', 'Hoàn tất'),
    ], default='upload')
    imported_count = fields.Integer(string='Số sản phẩm đã import', readonly=True)
    imported_product_ids = fields.Many2many(
        'product.template',
        string='Sản phẩm đã tạo',
        readonly=True,
    )
    error_text = fields.Text(string='Chi tiết lỗi', readonly=True)
    preview_text = fields.Html(string='Kết quả kiểm thử', readonly=True, sanitize=False)

    # Số lỗi mẫu tối đa hiển thị cho mỗi loại
    _MAX_SAMPLE = 5

    # Mapping: field_name → (search_field, domain)
    # Dùng để validate giá trị Excel (code/cid) đúng field trên comodel
    _FIELD_LOOKUP_CONFIG = {
        # Common
        'categ_id': ('code', []),
        'group_id': ('cid', []),
        'brand_id': ('code', []),
        'country_id': ('code', []),
        'uom_id': ('name', []),
        'warranty_id': ('code', []),
        'warranty_supplier_id': ('code', []),
        'warranty_retail_id': ('code', []),
        # Lens
        'lens_sph_id': ('name', [('power_type', '=', 'sph')]),
        'lens_cyl_id': ('name', [('power_type', '=', 'cyl')]),
        'lens_add_id': ('name', []),
        'lens_design1_id': ('cid', []),
        'lens_design2_id': ('cid', []),
        'lens_material_id': ('code', []),
        'lens_index_id': ('cid', []),
        'lens_uv_id': ('cid', []),
        'lens_cl_hmc_id': ('cid', []),
        'lens_cl_pho_id': ('cid', []),
        'lens_cl_tint_id': ('cid', []),
        # Frame
        'opt_frame_id': ('cid', []),
        'opt_frame_type_id': ('cid', []),
        'opt_shape_id': ('cid', []),
        'opt_ve_id': ('cid', []),
        'opt_temple_id': ('cid', []),
        'opt_material_ve_id': ('cid', []),
        'opt_material_temple_tip_id': ('cid', []),
        'opt_material_lens_id': ('cid', []),
        'opt_color_lens_id': ('cid', []),
        # Accessory
        'design_id': ('cid', []),
        'shape_id': ('cid', []),
        'material_id': ('cid', []),
        'color_id': ('cid', []),
    }

    # Reverse mapping: display code → real field name
    _CODE_TO_FIELD = {v: k for k, v in ProductExportTemplateWizard._FIELD_CODE_OVERRIDES.items()}

    def action_test(self):
        """Parse Excel và validate dữ liệu mà không import."""
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Vui lòng chọn file Excel.'))

        raw = base64.b64decode(self.file_data)
        header, rows, errors = self._parse_excel(raw)

        if errors:
            self.write({
                'state': 'preview',
                'preview_text': self._html_error_panel(
                    _('Lỗi khi đọc file'), '<br/>'.join(errors)),
            })
            return self._reopen()

        if not rows:
            self.write({
                'state': 'preview',
                'preview_text': self._html_error_panel(
                    _('Lỗi'), _('File không có dữ liệu.')),
            })
            return self._reopen()

        product_fields = self.env['product.template']._fields
        virtual_columns = set(ProductExportTemplateWizard._VIRTUAL_IMPORT_COLUMNS)
        col_map = {h: i for i, h in enumerate(header) if h}
        issues = []

        # Cột không nhận dạng
        unknown = [
            h for h in header
            if h and h not in product_fields and h not in virtual_columns and '/' not in h
        ]
        if unknown:
            issues.append({
                'level': 'warn',
                'title': _('Cột không nhận dạng được'),
                'details': [', '.join(unknown)],
            })

        # Validate dữ liệu
        self._test_required_fields(issues, rows, col_map)
        self._test_duplicate_names(issues, rows, col_map)
        self._test_existing_names(issues, rows, col_map)
        self._test_relational_fields(issues, rows, col_map, product_fields)

        html = self._build_preview_html(header, rows, col_map, issues)
        self.write({'state': 'preview', 'preview_text': html})
        return self._reopen()

    # ── HTML builders ──

    _LEVEL_STYLES = {
        'error': ('danger', '#dc3545'),
        'warn': ('warning', '#856404'),
        'ok': ('success', '#155724'),
    }

    def _build_preview_html(self, header, rows, col_map, issues):
        """Tạo HTML preview cho kết quả kiểm thử."""
        parts = []

        # Tổng quan
        col_tags = ''.join(
            '<span class="badge text-bg-secondary me-1 mb-1">%s</span>' % h
            for h in header if h
        )
        lbl_overview = _('Tổng quan')
        lbl_cols = _('Số cột')
        lbl_rows = _('Số dòng dữ liệu')
        parts.append(
            '<div class="card mb-3">'
            '<div class="card-header fw-bold">%s</div>'
            '<div class="card-body">'
            '<table class="table table-sm mb-2" style="width:auto;">'
            '<tr><td class="text-muted pe-3">%s</td><td class="fw-bold">%s</td></tr>'
            '<tr><td class="text-muted pe-3">%s</td><td class="fw-bold">%s</td></tr>'
            '</table>'
            '<div>%s</div>'
            '</div></div>' % (lbl_overview, lbl_cols, len(header),
                              lbl_rows, len(rows), col_tags)
        )

        # Issues
        if issues:
            rows_html = []
            for issue in issues:
                level_style = self._LEVEL_STYLES.get(issue['level'], ('secondary', '#6c757d'))
                color = level_style[1]
                title = '<strong style="color:%s;">%s</strong>' % (color, issue['title'])
                detail_items = ''.join(
                    '<li>%s</li>' % d for d in issue.get('details', []))
                detail_html = '<ul class="mb-0 ps-3">%s</ul>' % detail_items if detail_items else ''
                rows_html.append(
                    '<div class="border-start border-3 ps-3 mb-2" style="border-color:%s !important;">'
                    '%s%s</div>' % (color, title, detail_html)
                )
            lbl_detail = _('Chi tiết kiểm tra')
            parts.append(
                '<div class="card mb-3">'
                '<div class="card-header fw-bold">%s</div>'
                '<div class="card-body">%s</div></div>' % (lbl_detail, ''.join(rows_html))
            )

        # Kết quả
        has_errors = any(i['level'] == 'error' for i in issues)
        has_warns = any(i['level'] == 'warn' for i in issues)
        if has_errors:
            badge = 'danger'
            error_count = sum(1 for i in issues if i['level'] == 'error')
            msg = _('Phát hiện %s lỗi. Không thể import.') % error_count
        elif has_warns:
            badge = 'warning'
            msg = _('Phát hiện %s cảnh báo. Vui lòng kiểm tra trước khi import.') % len(issues)
        else:
            badge = 'success'
            msg = _('Không phát hiện lỗi. Sẵn sàng import.')

        lbl_result = _('Kết quả:')
        parts.append(
            '<div class="alert alert-%s mb-0" role="alert">'
            '<strong>%s</strong> %s</div>' % (badge, lbl_result, msg)
        )

        return '<div>%s</div>' % ''.join(parts)

    @staticmethod
    def _html_error_panel(title, body):
        return (
            '<div class="alert alert-danger" role="alert">'
            '<strong>%s</strong><br/>%s</div>' % (title, body)
        )

    # ── Validation methods ──

    def _test_required_fields(self, issues, rows, col_map):
        """Kiểm tra trường bắt buộc (name) không được trống."""
        required = ['name']
        for field_name in required:
            if field_name not in col_map:
                issues.append({
                    'level': 'error',
                    'title': _('Thiếu cột bắt buộc: %s') % field_name,
                })
                continue
            idx = col_map[field_name]
            empty_rows = [i + 1 for i, row in enumerate(rows) if not row[idx].strip()]
            if empty_rows:
                sample = empty_rows[:self._MAX_SAMPLE]
                extra = len(empty_rows) - self._MAX_SAMPLE
                detail = _('Dòng: %s') % ', '.join(str(r) for r in sample)
                if extra > 0:
                    detail += _(' ... và %s dòng khác') % extra
                issues.append({
                    'level': 'error',
                    'title': _('%s trống ở %s dòng') % (field_name, len(empty_rows)),
                    'details': [detail],
                })

    def _test_duplicate_names(self, issues, rows, col_map):
        """Kiểm tra name trùng trong file."""
        if 'name' not in col_map:
            return
        idx = col_map['name']
        seen = {}
        duplicates = {}
        for i, row in enumerate(rows):
            name = row[idx].strip()
            if not name:
                continue
            if name in seen:
                duplicates.setdefault(name, [seen[name]]).append(i + 1)
            else:
                seen[name] = i + 1

        if not duplicates:
            return

        details = []
        sample = list(duplicates.keys())[:self._MAX_SAMPLE]
        for name in sample:
            row_nums = ', '.join(str(r) for r in duplicates[name][:self._MAX_SAMPLE])
            details.append('"%s" (dòng: %s)' % (name, row_nums))
        if len(duplicates) > self._MAX_SAMPLE:
            details.append(_('... và %s tên khác') % (len(duplicates) - self._MAX_SAMPLE))
        issues.append({
            'level': 'error',
            'title': _('Tên trùng trong file: %s tên') % len(duplicates),
            'details': details,
        })

    def _test_existing_names(self, issues, rows, col_map):
        """Kiểm tra name đã tồn tại trong DB."""
        if 'name' not in col_map:
            return
        idx = col_map['name']
        unique_names = list({row[idx].strip() for row in rows if row[idx].strip()})
        if not unique_names:
            return

        existing = self.env['product.template'].with_context(active_test=False).search_read(
            [('name', 'in', unique_names)],
            ['name'],
        )
        existing_names = [r['name'] for r in existing if r['name']]
        if not existing_names:
            return

        details = []
        sample = existing_names[:10]
        details.append(', '.join(sample))
        if len(existing_names) > 10:
            details.append(_('... và %s tên khác') % (len(existing_names) - 10))
        issues.append({
            'level': 'error',
            'title': _('Tên đã tồn tại trong hệ thống: %s tên') % len(existing_names),
            'details': details,
        })

    def _test_relational_fields(self, issues, rows, col_map, product_fields):
        """Kiểm tra giá trị Many2one (code/cid) có tồn tại trong hệ thống."""
        for field_name, idx in col_map.items():
            if '/' in field_name or field_name not in product_fields:
                continue
            field = product_fields[field_name]
            if field.type != 'many2one':
                continue

            raw_values = {row[idx].strip() for row in rows if row[idx].strip()}
            if not raw_values:
                continue

            values = raw_values

            lookup = self._FIELD_LOOKUP_CONFIG.get(field_name)
            if lookup:
                search_field, domain = lookup
            else:
                CoModel = self.env[field.comodel_name]
                search_field = CoModel._rec_name or 'name'
                domain = []

            CoModel = self.env[field.comodel_name]
            if search_field not in CoModel._fields:
                continue

            found = CoModel.search_read(
                domain + [(search_field, 'in', list(values))],
                [search_field],
            )
            found_values = {r[search_field] for r in found if r.get(search_field)}
            not_found = values - found_values
            if not not_found:
                continue

            display_code = ProductExportTemplateWizard._FIELD_CODE_OVERRIDES.get(
                field_name, field_name)
            details = []
            sample = list(not_found)[:self._MAX_SAMPLE]
            details.append(', '.join('"%s"' % v for v in sample))
            if len(not_found) > self._MAX_SAMPLE:
                details.append(_('... và %s giá trị khác') % (len(not_found) - self._MAX_SAMPLE))
            issues.append({
                'level': 'warn',
                'title': _('%s: %s giá trị không tìm thấy trong %s') % (
                    display_code, len(not_found), field.comodel_name),
                'details': details,
            })

    def action_back_upload(self):
        """Quay lại bước upload."""
        self.ensure_one()
        self.write({
            'state': 'upload',
            'preview_text': False,
            'imported_count': 0,
            'imported_product_ids': [(5, 0, 0)],
            'error_text': False,
        })
        return self._reopen()

    def action_import(self):
        """Parse Excel và import sản phẩm qua product.template.load()."""
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Vui lòng chọn file Excel.'))

        raw = base64.b64decode(self.file_data)
        header, rows, errors = self._parse_excel(raw)

        if errors:
            self.write({
                'state': 'done',
                'imported_count': 0,
                'error_text': '\n'.join(errors),
            })
            return self._reopen()

        if not rows:
            self.write({
                'state': 'done',
                'imported_count': 0,
                'error_text': _('File không có dữ liệu.'),
            })
            return self._reopen()

        ProductTemplate = self.env['product.template'].with_context(
            import_file=True,
            vnop_import_product_type=self.product_type,
        )

        try:
            result = ProductTemplate.load(header, rows)
        except Exception as e:
            self.write({
                'state': 'done',
                'imported_count': 0,
                'error_text': str(e),
            })
            return self._reopen()

        messages = result.get('messages', [])
        error_messages = [m.get('message', '') for m in messages if m.get('type') == 'error']

        if error_messages:
            self.write({
                'state': 'done',
                'imported_count': 0,
                'error_text': '\n'.join(error_messages),
            })
            return self._reopen()

        ids = result.get('ids') or []
        self.write({
            'state': 'done',
            'imported_count': len(ids),
            'imported_product_ids': [(6, 0, ids)],
            'error_text': False,
        })
        return self._reopen()

    def _parse_excel(self, file_bytes):
        """Parse file Excel → (header_fields, data_rows, errors).

        Sử dụng logic tương tự base_import_product_template_inherit
        để tìm header row và data start row.
        """
        errors = []
        try:
            wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        except Exception as e:
            return [], [], [_('Không đọc được file Excel: %s') % str(e)]

        ws = wb.active
        if ws is None:
            wb.close()
            return [], [], [_('File Excel không có sheet nào.')]

        # Đọc tất cả rows
        all_rows = []
        for row in ws.iter_rows(values_only=True):
            all_rows.append([self._normalize_cell(c) for c in row])
        wb.close()

        if not all_rows:
            return [], [], [_('File Excel trống.')]

        # Tìm header row (dòng chứa technical field names)
        product_fields = set(self.env['product.template']._fields)
        header_index = self._find_header_index(all_rows, product_fields)

        if header_index is None:
            return [], [], [_('Không tìm thấy dòng header chứa tên trường kỹ thuật (vd: name, categ_code, brand_code...).')]

        header = [self._translate_token(self._normalize_cell(c))
                  for c in all_rows[header_index]]

        # Tìm data start row
        data_start = self._find_data_start(all_rows, header_index, header, product_fields)

        # Build data rows
        header_len = len(header)
        data_rows = []
        for row in all_rows[data_start:]:
            # Bỏ dòng trống
            if all(not self._normalize_cell(c) for c in row):
                continue
            padded = list(row) + [''] * max(0, header_len - len(row))
            data_rows.append(padded[:header_len])

        if not data_rows:
            errors.append(_('File không có dữ liệu (chỉ có header).'))

        return header, data_rows, errors

    def _translate_token(self, token):
        """Translate display code → real field name nếu có."""
        return self._CODE_TO_FIELD.get(token, token)

    def _find_header_index(self, rows, product_fields):
        """Tìm dòng header chứa technical field names (hỗ trợ cả display codes)."""
        marker_fields = {
            'categ_id', 'group_id', 'uom_id', 'brand_id',
            'len_type', 'opt_sku', 'opt_model',
            'design_id', 'shape_id', 'material_id', 'color_id',
        }
        # Thêm display codes tương ứng vào marker
        code_overrides = ProductExportTemplateWizard._FIELD_CODE_OVERRIDES
        marker_display = {code_overrides.get(f, f) for f in marker_fields
                          if f in code_overrides}
        all_markers = marker_fields | marker_display

        # Tập hợp tất cả recognized tokens (real fields + display codes)
        all_known = product_fields | set(self._CODE_TO_FIELD.keys())

        best_index = None
        best_score = -1

        for index, row in enumerate(rows):
            tokens = {self._normalize_cell(c) for c in row if self._normalize_cell(c)}
            matched = tokens & all_known
            if not matched:
                continue
            score = len(matched)
            has_name = 'name' in matched
            has_marker = bool(matched & all_markers)
            if has_name and has_marker and score > best_score:
                best_index = index
                best_score = score

        if best_index is not None:
            return best_index

        # Fallback: bất kỳ dòng nào có >= 3 field match
        for index, row in enumerate(rows):
            tokens = {self._normalize_cell(c) for c in row if self._normalize_cell(c)}
            score = len(tokens & all_known)
            if score >= 3 and score > best_score:
                best_index = index
                best_score = score

        return best_index

    def _find_data_start(self, rows, header_index, header_tokens, product_fields):
        """Tìm dòng bắt đầu data (bỏ qua label/hint rows)."""
        key_fields = {
            'name', 'default_code', 'standard_price', 'list_price',
            'len_type', 'opt_model', 'opt_sku',
        }
        # Thêm cả real field names và display codes cho key fields
        key_display = {
            'categ_code', 'group_cid', 'uom_name', 'brand_code',
            'categ_id', 'group_id', 'uom_id', 'brand_id',
            'design_cid', 'shape_cid', 'design_id', 'shape_id',
        }
        key_fields = key_fields | key_display
        key_indices = [i for i, t in enumerate(header_tokens) if t in key_fields]
        header_len = len(header_tokens)

        for row_index in range(header_index + 1, len(rows)):
            row = rows[row_index]
            non_empty = [
                i for i in range(min(len(row), header_len))
                if self._normalize_cell(row[i])
            ]
            if not non_empty:
                continue
            # Nếu dòng này overlap với key columns → đây là data
            if key_indices and any(i in non_empty for i in key_indices):
                return row_index
            if len(non_empty) >= 2:
                return row_index

        return len(rows)

    @staticmethod
    def _normalize_cell(value):
        if value in (None, False):
            return ''
        text = str(value).strip()
        if not text or text.lower() in ('none', 'null', 'nan'):
            return ''
        return text

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
