# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .amount_to_text_vi import amount_to_text_vi


class AccountMove(models.Model):
    _inherit = "account.move"

    amount_text_vi = fields.Char(
        string="Số tiền bằng chữ",
        compute="_compute_amount_text_vi",
    )

    @api.depends("amount_total", "currency_id")
    def _compute_amount_text_vi(self):
        for move in self:
            if move.currency_id and move.currency_id.name == "VND":
                move.amount_text_vi = amount_to_text_vi(move.amount_total, "đồng")
            else:
                move.amount_text_vi = amount_to_text_vi(move.amount_total, move.currency_id.name or "")
