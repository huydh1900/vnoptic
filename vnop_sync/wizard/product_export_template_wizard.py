import base64
import csv
from io import BytesIO, StringIO

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError


class ProductExportTemplateWizard(models.TransientModel):
    _name = 'product.export.template.wizard'
    _description = 'Export Product Template Wizard'

    _COMPANY_TITLE = 'CÔNG TY TNHH CÔNG NGHỆ QUANG HỌC VIỆT NAM'
    _COMPANY_ADDRESS = 'Số 63 phố Lê Duẩn, Phường Cửa Nam, Quận Hoàn Kiếm, Thành phố Hà Nội, Việt Nam'

    _TYPE_CONFIG = {
        'mat': {
            'template_key': 'Mat',
            'import_key': 'lens',
            'file_key': 'mat',
            'display_name': 'Mắt kính',
        },
        'gong': {
            'template_key': 'Gong',
            'import_key': 'frame',
            'file_key': 'gong',
            'display_name': 'Gọng kính',
        },
        'phukien': {
            'template_key': 'Phu kien',
            'import_key': 'accessory',
            'file_key': 'phu_kien',
            'display_name': 'Phụ kiện',
        },
    }

    _FIELD_LABEL_OVERRIDES = {
        'default_code': 'Mã sản phẩm',
        'image_1920': 'Hình ảnh (URL)',
        'name': 'Tên đầy đủ',
        'x_eng_name': 'Tên tiếng Anh',
        'categ_id': 'Nhóm',
        'group_id': 'Nhóm sản phẩm',
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
        'description_sale': 'Mô tả bán hàng',
        'taxes_id': 'Thuế bán',
        'supplier_taxes_id': 'Thuế mua',
        'product_status': 'Trạng thái',
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
        ('mat', 'Mắt kính'),
        ('gong', 'Gọng kính'),
        ('phukien', 'Phụ kiện'),
    ], string='Loại sản phẩm', required=True)

    export_format = fields.Selection([
        ('xlsx', 'XLSX'),
        ('csv', 'CSV'),
    ], string='Định dạng', required=True, default='xlsx')

    export_file = fields.Binary('File mẫu', readonly=True)

    @api.model
    def _get_template_payload(self, product_type, file_format='xlsx'):
        config = self._TYPE_CONFIG.get(product_type)
        if not config:
            raise UserError('Loại sản phẩm không hợp lệ.')

        if file_format not in ('xlsx', 'csv'):
            file_format = 'xlsx'

        product_model = self.env['product.template']
        templates = product_model._vnop_export_templates()
        fields_list = templates.get(config['template_key']) or []
        fields_list = self._prepare_fields_for_export(product_model, fields_list)
        if not fields_list:
            raise UserError('Không tìm thấy danh sách cột cho template đã chọn.')

        required_fields = set(
            product_model._VNOP_REQUIRED_COMMON + product_model._VNOP_REQUIRED_BY_TYPE[config['import_key']]
        )
        required_fields &= set(fields_list)

        if file_format == 'csv':
            content = self._build_csv_template(product_model, fields_list, required_fields, config)
            return {
                'content': content,
                'filename': f"Bảng_import_{config['file_key']}.csv",
                'mimetype': 'text/csv; charset=utf-8',
            }

        content = self._build_xlsx_template(product_model, fields_list, required_fields, config)
        return {
            'content': content,
            'filename': f"Bảng_mẫu_import_{config['file_key']}.xlsx",
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }

    def _prepare_fields_for_export(self, product_model, raw_fields):
        fields_list = []
        seen = set()

        for field_name in raw_fields:
            if field_name in product_model._fields and field_name not in seen:
                fields_list.append(field_name)
                seen.add(field_name)

        # New templates should not expose default_code for manual input.
        if 'default_code' in seen:
            fields_list = [field_name for field_name in fields_list if field_name != 'default_code']
            seen.remove('default_code')

        if 'image_1920' in product_model._fields and 'image_1920' not in seen:
            if 'name' in fields_list:
                insert_at = fields_list.index('name') + 1
            else:
                insert_at = 0
            fields_list.insert(insert_at, 'image_1920')
            seen.add('image_1920')

        if 'description' in product_model._fields:
            fields_list = [name for name in fields_list if name != 'description']
            fields_list.append('description')

        for virtual_field in self._VIRTUAL_IMPORT_COLUMNS:
            if virtual_field not in seen:
                fields_list.append(virtual_field)
                seen.add(virtual_field)

        return fields_list

    def _label_for_field(self, product_model, field_name):
        if field_name in self._FIELD_LABEL_OVERRIDES:
            return self._FIELD_LABEL_OVERRIDES[field_name]
        if field_name in self._VIRTUAL_FIELD_LABELS:
            return self._VIRTUAL_FIELD_LABELS[field_name]
        field = product_model._fields[field_name]
        return field.string or field_name

    def _note_for_field(self, product_model, field_name, is_required):
        if field_name == 'supplier_ref':
            required_text = 'Bắt buộc nhập.' if is_required else 'Tùy chọn.'
            return f"{required_text} Nhập ref nhà cung cấp (ví dụ: 5005, 5018)."

        if field_name == 'currency_id':
            required_text = 'Bắt buộc nhập.' if is_required else 'Tùy chọn.'
            return f"{required_text} Nhập mã/tên tiền tệ (ví dụ: USD, CNY)."

        field = product_model._fields[field_name]
        required_text = 'Bắt buộc nhập.' if is_required else 'Tùy chọn.'

        if field.type == 'many2one':
            hint = 'Nhập mã hoặc tên dữ liệu đã tồn tại trên hệ thống.'
        elif field.type in ('many2many', 'one2many'):
            hint = 'Nhập nhiều giá trị, ngăn cách bởi dấu phẩy (,).'
        elif field.type in ('float', 'integer', 'monetary'):
            hint = 'Nhập số, không dùng ký tự đặc biệt.'
        elif field.type == 'boolean':
            hint = 'Nhập 1/0, True/False hoặc Có/Không.'
        elif field.type == 'selection':
            hint = 'Nhập đúng giá trị lựa chọn theo cấu hình hệ thống.'
        else:
            hint = 'Nhập dữ liệu text theo quy định nghiệp vụ.'

        return f"{required_text} {hint}"

    def _build_xlsx_template(self, product_model, fields_list, required_fields, config):
        stream = BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})

        sheet = workbook.add_worksheet('Mẫu_nhập_liệu')
        guide = workbook.add_worksheet('Hướng_dẫn')

        last_col = max(0, len(fields_list) - 1)
        required_bg = '#F9CB9C'
        optional_bg = '#CFE2F3'

        title_style = workbook.add_format({
            'bold': True,
            'font_color': '#0B4EA2',
            'font_size': 18,
            'align': 'left',
            'valign': 'vcenter',
        })
        subtitle_style = workbook.add_format({
            'font_color': '#3C4F65',
            'italic': True,
            'font_size': 11,
            'align': 'left',
            'valign': 'vcenter',
        })
        required_style = workbook.add_format({
            'bold': True,
            'bg_color': required_bg,
            'border': 1,
            'text_wrap': True,
            'align': 'center',
            'valign': 'vcenter',
        })
        optional_style = workbook.add_format({
            'bold': True,
            'bg_color': optional_bg,
            'border': 1,
            'text_wrap': True,
            'align': 'center',
            'valign': 'vcenter',
        })
        code_required_style = workbook.add_format({
            'bg_color': required_bg,
            'font_color': '#8A2D00',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })
        code_optional_style = workbook.add_format({
            'bg_color': optional_bg,
            'font_color': '#0B4EA2',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })

        sheet.merge_range(0, 0, 0, last_col, self._COMPANY_TITLE, title_style)
        sheet.merge_range(1, 0, 1, last_col, self._COMPANY_ADDRESS, subtitle_style)
        sheet.set_row(0, 28)
        sheet.set_row(1, 20)
        sheet.set_row(2, 8)
        sheet.set_row(3, 30)
        sheet.set_row(4, 24)

        for col, field_name in enumerate(fields_list):
            label = self._label_for_field(product_model, field_name)
            is_required = field_name in required_fields
            vi_style = required_style if is_required else optional_style
            code_style = code_required_style if is_required else code_optional_style

            sheet.write(3, col, label, vi_style)
            sheet.write(4, col, field_name, code_style)
            sheet.write_comment(3, col, self._note_for_field(product_model, field_name, is_required))

            col_width = min(max(len(label), len(field_name), 14) + 2, 44)
            sheet.set_column(col, col, col_width)

        sheet.freeze_panes(5, 0)
        sheet.autofilter(4, 0, 4, last_col)

        guide_title = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#0B4EA2'})
        guide_head = workbook.add_format({'bold': True, 'bg_color': '#E8EEF7', 'border': 1})
        guide_text = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1})
        guide_icon_required = workbook.add_format({
            'bg_color': required_bg,
            'font_color': '#FFFFFF',
            'bold': True,
            'font_size': 16,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })
        guide_icon_optional = workbook.add_format({
            'bg_color': optional_bg,
            'font_color': '#FFFFFF',
            'bold': True,
            'font_size': 16,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })

        guide.write(0, 0, f"HƯỚNG DẪN NHẬP LIỆU - {config['display_name']}", guide_title)
        guide.write(2, 0, 'Mục', guide_head)
        guide.write(2, 1, 'Nội dung', guide_head)
        guide.write(3, 0, 'Dòng 1', guide_text)
        guide.write(3, 1, 'Thông tin tên công ty (tiêu đề mẫu).', guide_text)
        guide.write(4, 0, 'Dòng 2', guide_text)
        guide.write(4, 1, 'Địa chỉ công ty (dòng mô tả phụ).', guide_text)
        guide.write(5, 0, 'Dòng 4', guide_text)
        guide.write(5, 1, 'Tên cột tiếng Việt để người dùng dễ nhìn.', guide_text)
        guide.write(6, 0, 'Dòng 5', guide_text)
        guide.write(6, 1, 'Mã trường kỹ thuật dùng cho import.', guide_text)
        guide.write(7, 0, 'Từ dòng 6 trở đi', guide_text)
        guide.write(7, 1, 'Dữ liệu người dùng nhập, mỗi sản phẩm 1 dòng.', guide_text)
        guide.write(8, 0, '●', guide_icon_required)
        guide.write(8, 1, 'Cột bắt buộc nhập.', guide_text)
        guide.write(9, 0, '●', guide_icon_optional)
        guide.write(9, 1, 'Cột tùy chọn.', guide_text)
        guide.set_column(0, 0, 24)
        guide.set_column(1, 1, 86)

        workbook.close()
        return stream.getvalue()

    def _build_csv_template(self, product_model, fields_list, required_fields, config):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([self._COMPANY_TITLE])
        writer.writerow([self._COMPANY_ADDRESS])
        writer.writerow([])
        writer.writerow([self._label_for_field(product_model, field_name) for field_name in fields_list])
        writer.writerow(fields_list)
        writer.writerow([])
        writer.writerow([
            f"GHI CHÚ ({config['display_name']}): Cột bắt buộc = {', '.join(sorted(required_fields))}"
        ])
        return output.getvalue().encode('utf-8-sig')

    def action_export_template(self):
        self.ensure_one()
        payload = self._get_template_payload(self.product_type, self.export_format)
        self.export_file = base64.b64encode(payload['content'])
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/?model=product.export.template.wizard&id=%s&field=export_file&download=true&filename=%s' % (self.id, payload['filename']),
            'target': 'self',
        }
