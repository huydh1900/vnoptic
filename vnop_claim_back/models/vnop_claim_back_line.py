# -*- coding: utf-8 -*-
from odoo import api, fields, models


class VnopClaimBackLine(models.Model):
    _name = 'vnop.claim.back.line'
    _description = 'Dòng saleout chi tiết'
    _order = 'sequence, sale_date, id'

    claim_id = fields.Many2one(
        comodel_name='vnop.claim.back',
        string='Claim back',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    sale_date = fields.Date(string='Ngày bán', required=True)
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Sản phẩm',
        required=True,
    )
    qty_saleout = fields.Float(
        string='Số lượng',
        required=True,
        default=1.0,
        digits=(16, 2),
    )
    unit_price_saleout = fields.Monetary(
        string='Đơn giá bán',
        required=True,
        currency_field='currency_id',
    )
    amount_saleout = fields.Monetary(
        string='Thành tiền',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    claim_unit_amount = fields.Monetary(
        string='Claim/đơn vị',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    claim_amount = fields.Monetary(
        string='Tiền claim',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    end_customer_vat = fields.Char(string='MST KH cuối')
    end_customer_name = fields.Char(string='Tên KH cuối')
    notes = fields.Char(string='Ghi chú')
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='claim_id.currency_id',
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='claim_id.company_id',
        store=True,
    )

    @api.depends('qty_saleout', 'unit_price_saleout', 'claim_id.claim_pct_used')
    def _compute_amounts(self):
        for line in self:
            claim_pct = line.claim_id.claim_pct_used or 0.0
            line.amount_saleout = line.qty_saleout * line.unit_price_saleout
            line.claim_unit_amount = line.unit_price_saleout * claim_pct / 100.0
            line.claim_amount = line.qty_saleout * line.claim_unit_amount
