# -*- coding: utf-8 -*-
import base64
from io import BytesIO

from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    user_id = fields.Many2one(string='Người phụ trách')

    amount_total_text = fields.Char(
        string='Bằng chữ',
        compute='_compute_amount_total_text',
    )

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_total_text(self):
        from num2words import num2words
        for order in self:
            amount = int(round(order.amount_total or 0))
            words = num2words(amount, lang='vi').capitalize()
            currency_name = order.currency_id.name if order.currency_id else ''
            order.amount_total_text = f"{words} {currency_name}".strip()

    def action_import_lines_excel(self):
        """Mở wizard import sale.order.line từ Excel."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order.line.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def action_download_template(self):
        """Tải Excel template mẫu cho sale.order.line."""
        self.ensure_one()
        from ..wizard.sale_order_line_import_wizard import SaleOrderLineImportWizard
        content = SaleOrderLineImportWizard.generate_template()
        attachment = self.env["ir.attachment"].create({
            "name": "import_san_pham.xlsx",
            "type": "binary",
            "datas": base64.b64encode(content),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % attachment.id,
            "target": "self",
        }

    def action_print_intem(self):
        """Sinh file xlsx tem cho các dòng sản phẩm trong SO và mở wizard preview.

        Mỗi sale.order.line sinh ra `product_uom_qty` dòng tem (làm tròn).
        Tái sử dụng template + helper `_intem_row_values()` từ vnop_product_portal.
        """
        self.ensure_one()
        try:
            import openpyxl
        except ImportError as exc:
            raise UserError(
                "Thiếu thư viện openpyxl. Liên hệ admin cài đặt: pip install openpyxl"
            ) from exc

        from odoo.addons.vnop_product_portal.models.product_template import (
            INTEM_TEMPLATE_PATH,
            ProductTemplate,
        )

        # Dedupe theo product.template — mỗi sản phẩm khác nhau → 1 dòng tem,
        # giữ thứ tự lần xuất hiện đầu tiên trong order_line.
        unique_tmpls = []
        seen = set()
        for line in self.order_line:
            if line.display_type or not line.product_id:
                continue
            tmpl = line.product_id.product_tmpl_id
            if tmpl.id in seen:
                continue
            seen.add(tmpl.id)
            unique_tmpls.append(tmpl)

        if not unique_tmpls:
            raise UserError("Đơn không có sản phẩm để in tem.")

        # Prefetch field cần thiết trên tất cả template 1 lượt.
        all_tmpls = self.env['product.template'].browse(
            [t.id for t in unique_tmpls]
        )
        all_tmpls.fetch(list(ProductTemplate._INTEM_PREFETCH_FIELDS))
        all_tmpls.country_id.fetch(['name'])
        all_tmpls.brand_id.fetch(['name'])
        all_tmpls.lens_index_id.fetch(['name'])
        all_tmpls.material_id.fetch(['name'])
        all_tmpls.opt_material_lens_id.fetch(['name'])
        all_tmpls.opt_frame_type_id.fetch(['name'])
        all_tmpls.lens_material_ids.fetch(['name'])
        all_tmpls.lens_coating_ids.fetch(['name'])

        # Map product.template.id → register_url của warranty.registration đầu
        # tiên trùng template trong SO. Mỗi template chỉ in 1 dòng tem (dedupe)
        # nên chọn registration đầu tiên là đủ.
        warranty_url_by_tmpl = {}
        regs = self.warranty_registration_ids.sorted('id')
        if regs:
            regs.fetch(['register_url', 'product_id'])
            for reg in regs:
                tmpl_id = reg.product_id.product_tmpl_id.id
                if (
                    tmpl_id
                    and tmpl_id not in warranty_url_by_tmpl
                    and reg.register_url
                ):
                    warranty_url_by_tmpl[tmpl_id] = reg.register_url

        wb = openpyxl.load_workbook(INTEM_TEMPLATE_PATH)
        ws = wb.active
        for tmpl in unique_tmpls:
            ws.append(tmpl._intem_row_values(
                warranty_qr_url=warranty_url_by_tmpl.get(tmpl.id, ''),
            ))
        total = len(unique_tmpls)

        buf = BytesIO()
        wb.save(buf)
        raw = buf.getvalue()
        buf.close()

        filename = f"intem_{(self.name or 'SO').replace('/', '_')}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(raw),
            'res_model': 'sale.order',
            'res_id': self.id,
            'mimetype': (
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            ),
        })
        wizard = self.env['sale.intem.preview.wizard'].create({
            'order_id': self.id,
            'attachment_id': attachment.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': f'In tem — {total} sản phẩm',
            'res_model': 'sale.intem.preview.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    partner_full_address = fields.Char(
        string='Địa chỉ cụ thể',
        compute='_compute_partner_full_address',
    )

    partner_vat = fields.Char(
        string='Mã số thuế',
        related='partner_id.vat',
        readonly=True,
    )

    @api.depends(
        'partner_id',
        'partner_id.street',
        'partner_id.ward_id',
        'partner_id.state_id',
        'partner_id.country_id',
    )
    def _compute_partner_full_address(self):
        for order in self:
            partner = order.partner_id
            if not partner:
                order.partner_full_address = ''
                continue
            parts = [
                partner.street or '',
                partner.ward_id.name if partner.ward_id else '',
                partner.state_id.name if partner.state_id else '',
                partner.country_id.name if partner.country_id else '',
            ]
            order.partner_full_address = ', '.join(p for p in parts if p)

    deposit_amount = fields.Monetary(
        string='Tiền đặt cọc',
        currency_field='currency_id',
        help='Số tiền khách đặt cọc trước khi giao hàng.',
    )

    dealer_tier_id = fields.Many2one(
        comodel_name='dealer.tier',
        related='partner_id.dealer_tier_id',
        string='Hạng đại lý',
        store=True,
        readonly=True,
        help='Hạng đại lý — quyết định chính sách giá và chiết khấu.',
    )

    partner_credit_available = fields.Monetary(
        string='Hạn mức công nợ còn lại',
        compute='_compute_partner_credit_available',
        currency_field='currency_id',
        help='Hạn mức công nợ còn lại sau khi trừ đơn hiện tại. Âm = vượt hạn mức.',
    )

    @api.depends('partner_id', 'amount_total')
    def _compute_partner_credit_available(self):
        for order in self:
            partner = order.partner_id
            if partner:
                order.partner_credit_available = (
                    partner.credit_limit - partner.credit - order.amount_total
                )
            else:
                order.partner_credit_available = 0.0
