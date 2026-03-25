# -*- coding: utf-8 -*-
from odoo import fields, models


class ContractDocumentType(models.Model):
    _name = "contract.document.type"
    _description = "Loại chứng từ yêu cầu theo hợp đồng"
    _order = "name"

    name = fields.Char(string="Tên chứng từ", required=True)

