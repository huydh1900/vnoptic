# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class Contract(models.Model):
    _inherit = "contract"

    delivery_schedule_ids = fields.One2many(
        "delivery.schedule",
        "contract_id",
        string="Lịch giao hàng",
        readonly=True,
    )
    delivery_schedule_count = fields.Integer(
        string="Lịch giao hàng",
        compute="_compute_delivery_schedule_count",
    )
    purchase_order_count = fields.Integer(
        string="Đơn mua",
        compute="_compute_purchase_order_count",
    )

    def _compute_delivery_schedule_count(self):
        for rec in self:
            rec.delivery_schedule_count = len(rec.delivery_schedule_ids)

    def _compute_purchase_order_count(self):
        PO = self.env['purchase.order']
        for rec in self:
            rec.purchase_order_count = PO.search_count([('contract_id', '=', rec.id)])

    def action_view_purchase_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Đơn mua hàng',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }

    def action_view_delivery_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Lịch giao hàng",
            "res_model": "delivery.schedule",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "context": {
                "default_contract_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_company_id": self.company_id.id,
            },
            "target": "current",
        }

    def action_create_delivery_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Tạo lịch giao hàng"),
            "res_model": "delivery.schedule",
            "view_mode": "form",
            "context": {
                "default_contract_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_company_id": self.company_id.id,
                "default_delivery_datetime": self.shipment_date,
            },
            "target": "current",
        }
