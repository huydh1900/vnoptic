# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PurchaseOfferApprovalRule(models.Model):
    _name = "purchase.offer.approval.rule"
    _description = "Quy tắc phê duyệt đề nghị mua hàng"
    _order = "sequence, min_amount"

    name = fields.Char(string="Tên quy tắc", required=True)
    sequence = fields.Integer(string="Thứ tự", default=10)
    active = fields.Boolean(default=True)

    min_amount = fields.Monetary(
        string="Giá trị từ",
        currency_field="currency_id",
        default=0.0,
        help="Quy tắc áp dụng khi tổng giá trị đề nghị >= giá trị này.",
    )
    max_amount = fields.Monetary(
        string="Giá trị đến",
        currency_field="currency_id",
        default=0.0,
        help="Quy tắc áp dụng khi tổng giá trị đề nghị < giá trị này. "
             "Để 0 nếu không giới hạn trên.",
    )
    approver_id = fields.Many2one(
        "res.users",
        string="Người phê duyệt",
        help="Để trống nếu chưa xác định người duyệt. "
             "Khi duyệt sẽ báo lỗi yêu cầu cấu hình.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    @api.constrains("min_amount", "max_amount")
    def _check_amount_range(self):
        for rec in self:
            if rec.min_amount < 0 or rec.max_amount < 0:
                raise ValidationError(_("Giá trị ngưỡng không được âm."))
            if rec.max_amount and rec.max_amount <= rec.min_amount:
                raise ValidationError(
                    _("Giá trị đến phải lớn hơn giá trị từ (hoặc để 0 nếu không giới hạn).")
                )

    @api.model
    def _find_rule_for_amount(self, amount, company):
        """Trả về rule khớp với amount trong phạm vi công ty.

        Rule khớp khi: min_amount <= amount < max_amount (max_amount=0 nghĩa là
        không giới hạn trên). Nếu nhiều rule khớp, dùng sequence nhỏ nhất.
        """
        rules = self.search([("company_id", "=", company.id)])
        for rule in rules:
            if amount < rule.min_amount:
                continue
            if rule.max_amount and amount >= rule.max_amount:
                continue
            return rule
        return self.browse()
