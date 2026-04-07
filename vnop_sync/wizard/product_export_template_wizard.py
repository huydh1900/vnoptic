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
        },
        'frame': {
            'template_key': 'Gong',
            'file_key': 'gong',
            'display_name': 'Gọng kính',
        },
        'accessory': {
            'template_key': 'Phu kien',
            'file_key': 'phu_kien',
            'display_name': 'Phụ kiện',
        },
    }

    _FIELD_LABEL_OVERRIDES = {
        'default_code': 'Mã sản phẩm',
        'image_1920': 'Hình ảnh (URL)',
        'name': 'Tên đầy đủ',
        'x_eng_name': 'Tên tiếng Anh',
        'categ_id': 'Danh mục',
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

        content = self._build_xlsx_template(product_model, fields_list)
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

    def _build_xlsx_template(self, product_model, fields_list):
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

            sheet.write(3, col, label, header_style)
            sheet.write(4, col, field_name, code_style)

            char_width = max(len(label), len(field_name))
            col_width = char_width * width_scale + 2
            sheet.set_column(col, col, col_width)

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
