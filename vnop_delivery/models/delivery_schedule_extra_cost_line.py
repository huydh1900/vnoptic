# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DeliveryScheduleExtraCostLine(models.Model):
    _name = 'delivery.schedule.extra.cost.line'
    _description = 'Chi phí bổ sung lịch giao'
    _order = 'id'

    schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Lịch giao',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Sản phẩm',
        required=True,
        domain="[('landed_cost_ok', '=', True)]",
    )
    amount = fields.Monetary(
        string='Số tiền',
        currency_field='currency_id',
        default=0.0,
    )
    split_method = fields.Selection(
        [
            ('equal', 'Chia đều'),
            ('by_quantity', 'Theo số lượng'),
            ('by_current_cost_price', 'Theo giá trị hiện tại'),
            ('by_weight', 'Theo khối lượng'),
            ('by_volume', 'Theo thể tích'),
        ],
        string='Phương pháp phân bổ',
        default='by_current_cost_price',
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='schedule_id.currency_id',
        store=True,
        readonly=True,
    )
    note = fields.Char(string='Ghi chú')

    @staticmethod
    def _default_split_method_from_product(product):
        tmpl = product.product_tmpl_id
        return tmpl.split_method_landed_cost or 'by_current_cost_price'

    def _sync_defaults_from_product(self):
        for rec in self.filtered(lambda r: r.product_id):
            rec.split_method = self._default_split_method_from_product(rec.product_id)

    @api.onchange('product_id')
    def _onchange_product_id_set_split_method(self):
        self._sync_defaults_from_product()

    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_defaults_from_product()
        return records
