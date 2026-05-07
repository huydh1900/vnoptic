# -*- coding: utf-8 -*-
import base64
import logging
import os
import time
from io import BytesIO

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

INTEM_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'xlsx', 'intem_template.xlsx',
)
INTEM_DATA_START_ROW = 2


class ProductTemplate(models.Model):
    """Add a portal QR (URL + image) that points to the public product page
    served by this module's controller (/product/qr/<id>).

    The existing `x_java_qr_url` and `qr_code` fields (vnop_sync) are left
    untouched — this is an additional, self-contained QR for the Odoo portal.
    """
    _inherit = 'product.template'

    qr_portal_url = fields.Char(
        string='QR Portal URL',
        compute='_compute_qr_portal_url',
        store=False,
        help='Public URL embedded in the portal QR code: <web.base.url>/product/<id>. '
             'Để trống cho sản phẩm có legacy_product_id (đã in tem QR cũ – không sinh QR mới).',
    )
    qr_portal_image = fields.Binary(
        string='QR Portal',
        compute='_compute_qr_portal_image',
        store=False,
        help='QR PNG (base64) encoding qr_portal_url',
    )

    def _compute_qr_portal_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        base_url = base_url.rstrip('/')
        for rec in self:
            # Sản phẩm cũ (đã có legacy_product_id) đã in QR Java ngoài thị trường.
            # Không sinh QR Odoo mới để tránh nhầm lẫn — controller sẽ resolve
            # URL cũ qua legacy_product_id sau khi domain trỏ về Odoo.
            if rec.id and not rec.legacy_product_id:
                rec.qr_portal_url = f"{base_url}/product/{rec.id}"
            else:
                rec.qr_portal_url = False

    @api.depends('qr_portal_url')
    def _compute_qr_portal_image(self):
        try:
            import qrcode
        except ImportError:
            _logger.warning("qrcode library not available; qr_portal_image will be empty.")
            for rec in self:
                rec.qr_portal_image = False
            return
        for rec in self:
            if not rec.qr_portal_url:
                rec.qr_portal_image = False
                continue
            img = qrcode.make(rec.qr_portal_url)
            buf = BytesIO()
            img.save(buf, format='PNG')
            rec.qr_portal_image = base64.b64encode(buf.getvalue()).decode()

    # ------------------------------------------------------------------
    # Helpers used by the portal controller (mirrors ProductTEM DTO from Java)
    # ------------------------------------------------------------------
    def _portal_get_serial(self):
        """Build serial string consistent with Java backend.
        Lens products: S{sph}/C{cyl}/A{add}; Frame products: opt_serial.
        """
        self.ensure_one()
        if self.classification_type == 'lens' or self.x_sph or self.x_cyl:
            sph = self.x_sph or '0.00'
            cyl = self.x_cyl or '0.00'
            add = ('%.2f' % self.x_add) if self.x_add else '0.00'
            return f"S{sph}/C{cyl}/A{add}"
        if self.opt_serial:
            return self.opt_serial
        return ''

    def _portal_get_specification(self):
        """Compose a short specification string from lens/opt fields."""
        self.ensure_one()
        parts = []
        if self.classification_type == 'lens' or self.lens_index_id:
            if self.lens_index_id:
                parts.append(f"Index {self.lens_index_id.name}")
            if self.lens_material_ids:
                parts.append('/'.join(self.lens_material_ids.mapped('name')))
            if self.lens_coating_ids:
                parts.append('/'.join(self.lens_coating_ids.mapped('name')))
            if self.x_diameter:
                parts.append(f"Ø{self.x_diameter:g}mm")
        else:
            if self.opt_frame_type_id:
                parts.append(self.opt_frame_type_id.name)
            if self.opt_lens_width or self.opt_bridge_width or self.opt_temple_width:
                parts.append(
                    f"{self.opt_lens_width or 0}-{self.opt_bridge_width or 0}-{self.opt_temple_width or 0}"
                )
            if self.opt_color:
                parts.append(self.opt_color)
        return ' • '.join(p for p in parts if p)

    def _portal_get_material(self):
        """Best-effort material label across lens / frame products."""
        self.ensure_one()
        if self.material_id:
            return self.material_id.name
        if self.lens_material_ids:
            return ', '.join(self.lens_material_ids.mapped('name'))
        if self.opt_material_lens_id:
            return self.opt_material_lens_id.name
        return ''

    def _portal_get_group(self):
        """Group label: classification > category."""
        self.ensure_one()
        if self.classification_id:
            return self.classification_id.name
        if self.categ_id:
            return self.categ_id.display_name
        return ''

    # ------------------------------------------------------------------
    # Xuất thông tin sản phẩm theo template "in tem"
    # ------------------------------------------------------------------
    # Field tối thiểu cần đọc trên product.template để build row export.
    # Khai báo tường minh để Odoo prefetch trong 1 query duy nhất cho cả
    # recordset thay vì lazy-load lặt vặt khi chạm tới từng cột.
    _INTEM_PREFETCH_FIELDS = (
        'name', 'display_name', 'barcode', 'default_code', 'list_price',
        'x_java_qr_url', 'qr_portal_url', 'legacy_product_id',
        'country_id', 'brand_id',
        'classification_type', 'classification_id', 'categ_id',
        'x_sph', 'x_cyl', 'x_add', 'x_diameter',
        'opt_serial', 'opt_lens_width', 'opt_bridge_width', 'opt_temple_width',
        'opt_color', 'opt_frame_type_id',
        'lens_index_id', 'lens_material_ids', 'lens_coating_ids',
        'material_id', 'opt_material_lens_id',
        'x_uses', 'x_guide', 'x_warning', 'x_preserve',
    )
    _INTEM_MAX_RECORDS = 10000

    def _intem_row_values(self):
        """Trả về list 17 phần tử khớp thứ tự cột A..Q của template intem.
        Cột trống (Date / Export / EA / Number) trả '' để giữ định dạng.
        """
        self.ensure_one()
        qr_url = self.x_java_qr_url or self.qr_portal_url or ''
        cid = self.barcode or self.default_code or ''
        return [
            qr_url,                                              # A Qr
            self.display_name or self.name or '',                # B Name
            cid,                                                 # C Cid
            self.country_id.name if self.country_id else '',     # D Country
            self.brand_id.name if self.brand_id else '',         # E TradeMark
            self._portal_get_serial(),                           # F Serial
            self._portal_get_material(),                         # G Material
            self._portal_get_specification(),                    # H Specification
            self.list_price or 0.0,                              # I Price
            '',                                                  # J Date
            '',                                                  # K Export
            '',                                                  # L EA
            self.x_uses or '',                                   # M Use
            self.x_guide or '',                                  # N Guide
            self.x_warning or '',                                # O Warning
            self.x_preserve or '',                               # P Preserve
            '',                                                  # Q Number
        ]

    def action_export_intem(self):
        """Sinh file Excel theo template tem, trả về act_url tải file.
        Áp dụng cho self là 1 hoặc nhiều product.template (gọi từ form button
        hoặc server action trên list view). Tối ưu cho 1k-5k record/lần.
        """
        if not self:
            raise UserError("Vui lòng chọn ít nhất 1 sản phẩm.")
        if len(self) > self._INTEM_MAX_RECORDS:
            raise UserError(
                f"Đang chọn {len(self):,} sản phẩm — vượt giới hạn "
                f"{self._INTEM_MAX_RECORDS:,}/lần. Vui lòng lọc bớt rồi xuất nhiều đợt."
            )
        try:
            import openpyxl
        except ImportError as exc:
            raise UserError(
                "Thiếu thư viện openpyxl. Liên hệ admin cài đặt: pip install openpyxl"
            ) from exc

        if not os.path.isfile(INTEM_TEMPLATE_PATH):
            raise UserError("Không tìm thấy template Excel mẫu trong module.")

        t0 = time.perf_counter()

        # Force batched prefetch: 1 SQL cho mọi field trực tiếp + 1 SQL/Many2one
        # cho mỗi quan hệ. Tránh lazy-load lặt vặt trong vòng for bên dưới.
        self.fetch(list(self._INTEM_PREFETCH_FIELDS))
        # Prefetch sub-records cho các Many2one cần đọc .name
        self.country_id.fetch(['name'])
        self.brand_id.fetch(['name'])
        self.lens_index_id.fetch(['name'])
        self.material_id.fetch(['name'])
        self.opt_material_lens_id.fetch(['name'])
        self.opt_frame_type_id.fetch(['name'])
        self.lens_material_ids.fetch(['name'])
        self.lens_coating_ids.fetch(['name'])

        wb = openpyxl.load_workbook(INTEM_TEMPLATE_PATH)
        ws = wb.active
        # ws.append() nhanh và đọc dễ hơn ws.cell(row, col) cho ghi tuần tự.
        for product in self:
            ws.append(product._intem_row_values())

        buf = BytesIO()
        wb.save(buf)
        raw = buf.getvalue()
        buf.close()

        if len(self) == 1:
            stem = self.default_code or str(self.id)
            filename = f"intem_{stem}.xlsx"
        else:
            ts = fields.Datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"intem_{len(self)}sp_{ts}.xlsx"

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(raw),
            'res_model': 'product.template',
            'res_id': self[0].id,
            'mimetype': (
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            ),
        })
        dt = time.perf_counter() - t0
        if len(self) >= 100:
            _logger.info(
                "intem export: %s sản phẩm, %s bytes, %.2fs",
                len(self), len(raw), dt,
            )
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
