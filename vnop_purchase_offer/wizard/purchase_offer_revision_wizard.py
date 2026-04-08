# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOfferRevisionWizard(models.TransientModel):
    _name = "purchase.offer.revision.wizard"
    _description = "Yêu cầu chỉnh sửa đề nghị mua hàng"

    offer_id = fields.Many2one("purchase.offer", string="Đề nghị mua hàng", required=True)
    reason = fields.Text(string="Lý do chỉnh sửa", required=True)

    def action_confirm(self):
        self.ensure_one()
        if self.offer_id.state != "waiting_approval":
            raise UserError(_("Chỉ đề nghị ở trạng thái Chờ duyệt mới được yêu cầu chỉnh sửa."))
        self.offer_id.write({
            "state": "draft",
            "revision_reason": self.reason,
        })
        self.offer_id.message_post(
            body=_("Yêu cầu chỉnh sửa: %s") % self.reason,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
