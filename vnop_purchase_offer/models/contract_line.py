# -*- coding: utf-8 -*-
from odoo import fields, models


class ContractLine(models.Model):
    _inherit = "contract.line"

    purchase_offer_line_id = fields.Many2one(
        "purchase.offer.line",
        string="Dòng Đề nghị mua hàng",
        copy=False,
    )
    purchase_offer_id = fields.Many2one(
        "purchase.offer",
        string="Đề nghị mua hàng",
        related="purchase_offer_line_id.offer_id",
        store=True,
        readonly=True,
    )
