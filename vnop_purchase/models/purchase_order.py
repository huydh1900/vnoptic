from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    vendor_document_ids = fields.Many2many(
        'ir.attachment',
        string="Chứng từ NCC (Phiếu xuất/Hóa đơn)",
        help="Upload bản mềm NCC gửi trước tại đây"
    )

    approver_id = fields.Many2one('res.users', string="Người duyệt")
    contract_id = fields.Many2one(
        'purchase.contract',
        string="Hợp đồng",
        domain="[('vendor_id','=',partner_id), ('state','=','active')]"
    )

    def button_need_edit(self):
        for order in self:
            order.state = 'draft'

    def action_send_approve(self):
        for order in self:
            # =========================
            # 1. Check có sản phẩm chưa
            # =========================
            if not order.approver_id:
                raise ValidationError(_("Bạn phải chọn Người duyệt!"))

            if not order.order_line:
                raise ValidationError(_("Đơn mua hàng phải có ít nhất 01 sản phẩm."))

            # =========================
            # 2. Check trùng sản phẩm
            # =========================
            product_lines = order.order_line.filtered(lambda l: l.product_id)

            product_count = {}
            for line in product_lines:
                product_count.setdefault(line.product_id, 0)
                product_count[line.product_id] += 1

            duplicated_products = [
                product.display_name
                for product, count in product_count.items()
                if count > 1
            ]

            if duplicated_products:
                raise ValidationError(
                    _("Sản phẩm bị trùng trong đơn mua hàng:\n- %s")
                    % "\n- ".join(duplicated_products)
                )

            # =========================
            # 3. Check file đính kèm
            # =========================
            attachments = order.vendor_document_ids

            if len(attachments) < 2:
                raise ValidationError(
                    _("Phải upload ít nhất 02 file chứng từ (Phiếu xuất + Hóa đơn).")
                )

            invalid_files = attachments.filtered(
                lambda a: a.mimetype != 'application/pdf'
                          and not (a.name or '').lower().endswith('.pdf')
            )

            if invalid_files:
                raise ValidationError(
                    _("Chỉ cho phép upload file PDF.\n"
                      "File không hợp lệ:\n- %s")
                    % "\n- ".join(invalid_files.mapped('name'))
                )

            order.state = 'to approve'

    @api.onchange('partner_id')
    def _onchange_partner_id_fill_partner_ref(self):
        if self.partner_id:
            self.partner_ref = self.partner_id.ref or False

    # @api.onchange('partner_ref')
    # def _onchange_partner_ref_fill_partner(self):
    #     if self.partner_ref:
    #         partner = self.env['res.partner'].search(
    #             [('ref', '=', self.partner_ref)],
    #             limit=1
    #         )
    #         if partner:
    #             self.partner_id = partner
