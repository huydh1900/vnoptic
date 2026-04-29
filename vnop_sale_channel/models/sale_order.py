# -*- coding: utf-8 -*-
import base64

from odoo import api, fields, models


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

    def check_stock_warning(self):
        """Trả list các SP thiếu tồn cho UI cảnh báo. Chỉ áp khi state in (draft, sent).

        Format: [{'name', 'ordered', 'available', 'uom'}, ...]
        Tối ưu cho đơn nhiều dòng:
        - Gom qty theo product (1 warning / SP, không lặp).
        - 1 lần batch compute qty_available cho cả recordset products
          (Odoo lazy-compute fields chạy theo lô khi access trên recordset).
        - Bỏ qua service / combo.
        """
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            return []

        qty_by_product = {}
        uom_by_product = {}
        for line in self.order_line:
            product = line.product_id
            if not product or product.type != 'consu' or line.product_uom_qty <= 0:
                continue
            qty_by_product[product.id] = qty_by_product.get(product.id, 0.0) + line.product_uom_qty
            uom_by_product.setdefault(product.id, line.product_uom.name or '')

        if not qty_by_product:
            return []

        products = self.env['product.product'].with_company(self.company_id).browse(list(qty_by_product))
        # Trigger batch compute 1 lần cho toàn recordset
        products.fetch(['default_code', 'display_name', 'qty_available'])

        warnings = []
        for product in products:
            ordered = qty_by_product[product.id]
            available = product.qty_available
            if available < ordered:
                warnings.append({
                    'name': product.default_code or product.display_name,
                    'ordered': ordered,
                    'available': available,
                    'uom': uom_by_product[product.id],
                })
        return warnings

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

    channel_type = fields.Selection(
        selection=[
            ('wholesale', 'Bán buôn'),
            ('retail', 'Bán lẻ'),
        ],
        string='Kênh bán',
        compute='_compute_channel_type',
        store=True,
        readonly=False,
        precompute=True,
        help='Kênh bán của đơn hàng. Mặc định lấy từ khách hàng, có thể chỉnh tay.',
    )

    @api.depends('partner_id')
    def _compute_channel_type(self):
        for order in self:
            if order.partner_id and order.partner_id.channel_type:
                order.channel_type = order.partner_id.channel_type
            elif not order.channel_type:
                order.channel_type = 'retail'

    @api.depends('channel_type')
    def _compute_pricelist_id(self):
        """Khi chọn kênh bán, tự động gán bảng giá khớp channel_type tương ứng.

        - Giữ bảng giá hiện tại nếu đã khớp kênh (hoặc bảng giá 'chung' - channel_type=False).
        - Ưu tiên bảng giá cùng kênh; nếu không có thì fallback logic gốc (theo partner).
        """
        super()._compute_pricelist_id()
        for order in self:
            if order.state != 'draft' or not order.channel_type:
                continue
            if order.pricelist_id and order.pricelist_id.channel_type in (order.channel_type, False):
                continue
            matching = self.env['product.pricelist'].search([
                ('channel_type', '=', order.channel_type),
                ('company_id', 'in', (False, order.company_id.id)),
            ], limit=1)
            if matching:
                order.pricelist_id = matching
