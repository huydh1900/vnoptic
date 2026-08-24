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
# Template có 2 dòng header (EN + VN) → dữ liệu bắt đầu từ dòng 3.
INTEM_DATA_START_ROW = 3
# Field cần đọc trên NCC chính để build cột "Xuất khẩu bởi" / "Địa chỉ".
_INTEM_PARTNER_FIELDS = [
    'name', 'street', 'street2', 'city', 'state_id', 'zip', 'country_id',
]


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

    def _intem_get_size(self):
        """Cột "Kích thước" của file tem: gộp Ngang mắt - Dài cầu - Dài càng.

        Gọng kính -> "53 - 18 - 148" (mm, bỏ phần thập phân thừa).
        Tròng kính không có 3 số này -> fallback đường kính.
        """
        self.ensure_one()

        def _fmt(val):
            return ('%g' % val) if val else ''

        # Mapping theo header import (product_import_wizard.HEADER_MAP):
        # "Ngang mắt" -> ngang_mat, "Dài cầu" -> opt_bridge_width,
        # "Dài càng" -> opt_temple_width.
        # Fallback opt_lens_width: dữ liệu sync từ Java đổ ngang mắt vào
        # opt_lens_width (ngang_mat chỉ có ở record import bằng Excel).
        parts = [
            _fmt(self.ngang_mat or self.opt_lens_width),
            _fmt(self.opt_bridge_width),
            _fmt(self.opt_temple_width),
        ]
        if any(parts):
            return ' - '.join(parts)
        if self.x_diameter:
            return 'Ø%gmm' % self.x_diameter
        return ''

    def _intem_get_material(self):
        """Cột "Vật liệu" của file tem: mặt trước + càng kính.

        VD: "Mặt trước: nhựa TR90, Càng: nhựa TR90+kim loại".
        Sản phẩm không phải gọng (tròng, phụ kiện) -> fallback về
        `_portal_get_material()`.
        """
        self.ensure_one()
        parts = []
        if self.opt_materials_front_ids:
            parts.append(
                'Mặt trước: %s'
                % '+'.join(self.opt_materials_front_ids.mapped('name'))
            )
        if self.opt_materials_temple_ids:
            parts.append(
                'Càng: %s'
                % '+'.join(self.opt_materials_temple_ids.mapped('name'))
            )
        if parts:
            return ', '.join(parts)
        return self._portal_get_material()

    def _intem_get_exporter(self):
        """(Tên, Địa chỉ) nhà xuất khẩu = NCC chính của sản phẩm."""
        self.ensure_one()
        partner = self.primary_supplier_id
        if not partner:
            return '', ''
        address = partner._display_address(without_company=True) or ''
        return partner.name or '', ' '.join(address.split())

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
        'x_java_qr_url', 'qr_portal_url', 'legacy_product_id', 'legacy_code',
        'country_id', 'brand_id',
        'classification_type', 'classification_id', 'categ_id',
        'x_sph', 'x_cyl', 'x_add', 'x_diameter',
        'opt_serial', 'opt_lens_width', 'opt_bridge_width', 'opt_temple_width',
        'ngang_mat', 'opt_color', 'opt_frame_type_id',
        'description_sale', 'primary_supplier_id',
        'lens_index_id', 'lens_material_ids', 'lens_coating_ids',
        'material_id', 'opt_material_lens_id',
        'opt_materials_front_ids', 'opt_materials_temple_ids',
        'x_uses', 'x_guide', 'x_warning', 'x_preserve',
    )
    _INTEM_MAX_RECORDS = 10000

    def _intem_row_values(self, warranty_qr_url=''):
        """Trả về list 19 phần tử khớp thứ tự cột A..S của template intem.

        Layout theo file mẫu khách hàng dùng để in tem:
        A Qr | B Name | C Cid | D (trống) | E Country | F TradeMark | G Serial |
        H Material | I Specification (Kích thước) | J Price | K Date |
        L Number | M Xuất khẩu bởi | N Địa chỉ | O Use | P Guide | Q Warning |
        R Preserve | S Mô tả chung.

        :param warranty_qr_url: URL QR bảo hành (warranty.registration.register_url)
            do caller truyền vào — vì warranty là per-SN, không thể derive ở cấp
            product.template. Caller (vd sale.order) phải build map template→URL.
            Ưu tiên hơn QR sản phẩm vì tem dán theo từng sản phẩm bán ra.
        """
        self.ensure_one()
        qr_url = warranty_qr_url or self.x_java_qr_url or self.qr_portal_url or ''
        # Ưu tiên mã 6 số khách nhập khi import (legacy_code) — đây là mã
        # in trên tem. Field tên "legacy" nhưng vẫn là mã đang dùng; barcode
        # Odoo tự sinh (dạng 26xxxxxx) chỉ là fallback khi chưa import mã 6 số.
        cid = self.legacy_code or self.barcode or self.default_code or ''
        exporter_name, exporter_address = self._intem_get_exporter()
        return [
            qr_url,                                              # A Qr
            self.display_name or self.name or '',                # B Name
            cid,                                                 # C Cid
            '',                                                  # D (trống)
            self.country_id.name if self.country_id else '',     # E Country
            self.brand_id.name if self.brand_id else '',         # F TradeMark
            self._portal_get_serial(),                           # G Serial
            self._intem_get_material(),                          # H Material
            self._intem_get_size(),                              # I Kích thước
            self.list_price or 0.0,                              # J Price
            fields.Date.context_today(self),                     # K Date
            '',                                                  # L Number
            exporter_name,                                       # M Xuất khẩu bởi
            exporter_address,                                    # N Địa chỉ
            self.x_uses or '',                                   # O Use
            self.x_guide or '',                                  # P Guide
            self.x_warning or '',                                # Q Warning
            self.x_preserve or '',                               # R Preserve
            self.description_sale or '',                         # S Mô tả chung
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
        self.primary_supplier_id.fetch(_INTEM_PARTNER_FIELDS)
        self.lens_index_id.fetch(['name'])
        self.material_id.fetch(['name'])
        self.opt_materials_front_ids.fetch(['name'])
        self.opt_materials_temple_ids.fetch(['name'])
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
