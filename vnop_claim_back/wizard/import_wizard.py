# -*- coding: utf-8 -*-
import base64
import io
import logging
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Cột Excel cố định: STT | Ngày bán | Mã SP | Tên SP | ĐVT | Số lượng | Đơn giá bán | Thành tiền | MST KH cuối | Tên KH cuối
EXPECTED_HEADERS = ['stt', 'ngày bán', 'mã sp', 'tên sp', 'đvt', 'số lượng', 'đơn giá bán', 'thành tiền', 'mst kh cuối', 'tên kh cuối']


def _first_day_last_month():
    today = date.today()
    first_this_month = today.replace(day=1)
    last_month = first_this_month.replace(day=1)
    # Go back one month
    if first_this_month.month == 1:
        last_month = first_this_month.replace(year=first_this_month.year - 1, month=12, day=1)
    else:
        last_month = first_this_month.replace(month=first_this_month.month - 1, day=1)
    return last_month


def _last_day_last_month():
    today = date.today()
    first_this_month = today.replace(day=1)
    import calendar
    if first_this_month.month == 1:
        year = first_this_month.year - 1
        month = 12
    else:
        year = first_this_month.year
        month = first_this_month.month - 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


class VnopClaimBackImportWizard(models.TransientModel):
    _name = 'vnop.claim.back.import.wizard'
    _description = 'Wizard upload saleout Excel'

    dealer_id = fields.Many2one(
        comodel_name='res.partner',
        string='Đại lý',
        required=True,
        domain=[('dealer_tier_id', '!=', False)],
    )
    period_from = fields.Date(
        string='Từ ngày',
        required=True,
        default=_first_day_last_month,
    )
    period_to = fields.Date(
        string='Đến ngày',
        required=True,
        default=_last_day_last_month,
    )
    excel_file = fields.Binary(string='File Excel', required=True)
    excel_filename = fields.Char(string='Tên file')
    preview_text = fields.Text(string='Xem trước', readonly=True)
    error_text = fields.Text(string='Cảnh báo / Lỗi', readonly=True)
    parsed = fields.Boolean(readonly=True, default=False)

    # Lưu kết quả parse tạm vào JSON để action_create dùng lại nếu đã parsed
    _parsed_lines_cache = None

    def action_parse(self):
        """Validate header, đọc tất cả dòng, khớp sản phẩm, cập nhật preview + error."""
        self.ensure_one()
        try:
            import openpyxl
        except ImportError:
            raise UserError(_('Thư viện openpyxl chưa được cài đặt.'))

        if not self.excel_file:
            raise UserError(_('Vui lòng chọn file Excel.'))

        wb = openpyxl.load_workbook(
            io.BytesIO(base64.b64decode(self.excel_file)), data_only=True
        )
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise UserError(_('File Excel trống.'))

        # Validate header (row đầu tiên)
        header_row = [str(cell).strip().lower() if cell is not None else '' for cell in rows[0]]
        if header_row != EXPECTED_HEADERS:
            raise UserError(
                _('Header không đúng định dạng.\nMong đợi: %s\nThực tế: %s')
                % (', '.join(EXPECTED_HEADERS), ', '.join(header_row))
            )

        company = self.env.company
        errors = []
        previews = []
        parsed_lines = []

        for row_idx, row in enumerate(rows[1:], start=2):
            # Skip dòng trống hoàn toàn
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue

            stt = row[0]
            sale_date_raw = row[1]
            product_code = str(row[2]).strip() if row[2] is not None else ''
            product_name = str(row[3]).strip() if row[3] is not None else ''
            # row[4] = ĐVT — bỏ qua
            qty_raw = row[5]
            price_raw = row[6]
            # row[7] = Thành tiền — tính lại từ qty * price
            end_customer_vat = str(row[8]).strip() if row[8] is not None else ''
            end_customer_name = str(row[9]).strip() if row[9] is not None else ''

            # Validate sale_date
            if isinstance(sale_date_raw, date):
                sale_date = sale_date_raw
            else:
                errors.append(_('Dòng %d: Ngày bán không hợp lệ (%s).') % (row_idx, sale_date_raw))
                continue

            # Validate qty
            try:
                qty = float(qty_raw or 0)
            except (ValueError, TypeError):
                errors.append(_('Dòng %d: Số lượng không hợp lệ (%s).') % (row_idx, qty_raw))
                continue

            # Validate price
            try:
                price = float(price_raw or 0)
            except (ValueError, TypeError):
                errors.append(_('Dòng %d: Đơn giá không hợp lệ (%s).') % (row_idx, price_raw))
                continue

            # Khớp sản phẩm
            product = False
            if product_code:
                product = self.env['product.product'].search(
                    [('default_code', '=', product_code), ('company_id', 'in', [False, company.id])],
                    limit=1,
                )
            if not product and product_name:
                product = self.env['product.product'].search(
                    [('name', 'ilike', product_name), ('company_id', 'in', [False, company.id])],
                    limit=1,
                )
            if not product:
                errors.append(
                    _('Dòng %d: Không tìm thấy sản phẩm (mã: %s, tên: %s). Dòng sẽ bị bỏ qua.')
                    % (row_idx, product_code, product_name)
                )
                continue

            parsed_lines.append({
                'sequence': int(stt) if stt and str(stt).strip().isdigit() else row_idx - 1,
                'sale_date': sale_date,
                'product_id': product.id,
                'qty_saleout': qty,
                'unit_price_saleout': price,
                'end_customer_vat': end_customer_vat,
                'end_customer_name': end_customer_name,
            })
            previews.append(
                '%s | %s | %s | %.2f | %.2f' % (
                    sale_date, product_code or product_name,
                    product.display_name, qty, price,
                )
            )

        # Lưu cache trên instance để action_create dùng lại
        self._parsed_lines_cache = parsed_lines

        self.write({
            'preview_text': '\n'.join(previews) if previews else _('(Không có dòng hợp lệ)'),
            'error_text': '\n'.join(errors) if errors else False,
            'parsed': True,
        })
        # Trả về action reload wizard để user xem preview
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_create(self):
        """Tạo vnop.claim.back state=uploaded từ kết quả parse."""
        self.ensure_one()
        if not self.parsed or self._parsed_lines_cache is None:
            # Tự động parse trước
            self.action_parse()

        parsed_lines = self._parsed_lines_cache or []
        if not parsed_lines:
            raise UserError(_('Không có dòng hợp lệ để tạo bản ghi. Vui lòng kiểm tra lại file.'))

        line_vals = [(0, 0, line) for line in parsed_lines]
        claim = self.env['vnop.claim.back'].create({
            'dealer_id': self.dealer_id.id,
            'period_from': self.period_from,
            'period_to': self.period_to,
            'excel_file': self.excel_file,
            'excel_filename': self.excel_filename,
            'state': 'uploaded',
            'line_ids': line_vals,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'vnop.claim.back',
            'res_id': claim.id,
            'view_mode': 'form',
            'target': 'current',
        }
