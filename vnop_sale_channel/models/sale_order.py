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
