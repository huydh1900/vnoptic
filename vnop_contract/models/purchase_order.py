# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    contract_id = fields.Many2one(
        "contract",
        string="Framework Contract",
        copy=False,
        index=True,
    )


