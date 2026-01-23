from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"


    state = fields.Selection(
        selection_add=[
            ('to_approve', 'Chờ duyệt'),
        ]
    )

    vendor_document_ids = fields.Many2many(
        'ir.attachment',
        string="Chứng từ NCC (Phiếu xuất/Hóa đơn)",
        help="Upload bản mềm NCC gửi trước tại đây"
    )

    def action_send_approve(self):
        for order in self:
            order.state = 'to_approve'

    def button_confirm(self):
        for order in self:
            attachments = order.vendor_document_ids

            if len(attachments) < 2:
                raise ValidationError("Phải upload ít nhất 02 file chứng từ (Phiếu xuất + Hóa đơn).")

            invalid_files = attachments.filtered(
                lambda a: a.mimetype != 'application/pdf'
                and not (a.name or '').lower().endswith('.pdf')
            )

            # if invalid_files:
            #     raise ValidationError(
            #         _("Chỉ cho phép upload file PDF.\n"
            #           "File không hợp lệ:\n- %s")
            #         % "\n- ".join(invalid_files.mapped('name'))
            #     )

        res = super(PurchaseOrder, self).button_confirm()

        # =========================
        # COPY ATTACHMENT SANG PICKING
        # =========================
        for order in self:
            if order.vendor_document_ids and order.picking_ids:
                for picking in order.picking_ids:
                    for attach in order.vendor_document_ids:
                        attach.copy({
                            'res_model': 'stock.picking',
                            'res_id': picking.id,
                        })

        return res
