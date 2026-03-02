# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class Contract(models.Model):
    _inherit = "contract"

    arrival_ids = fields.One2many("contract.arrival", "contract_id", string="Các lần về", readonly=True)
    arrival_count = fields.Integer(string="Số lần về", compute="_compute_arrival_count")

    def _compute_arrival_count(self):
        for rec in self:
            rec.arrival_count = len(rec.arrival_ids)

    def action_view_arrivals(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Các lần về"),
            "res_model": "contract.arrival",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "target": "current",
        }


class ContractArrival(models.Model):
    _name = "contract.arrival"
    _description = "Lần về theo hợp đồng"
    _order = "arrival_date desc, id desc"

    name = fields.Char(string="Mã lần về", required=True, readonly=True, copy=False, default=lambda self: _("Mới"))
    contract_id = fields.Many2one("contract", string="Hợp đồng", required=True, ondelete="cascade", index=True)
    delivery_schedule_id = fields.Many2one(
        "delivery.schedule",
        string="Lịch giao hàng",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(related="contract_id.partner_id", store=True, readonly=True)
    company_id = fields.Many2one(related="contract_id.company_id", store=True, readonly=True)
    arrival_date = fields.Date(string="Ngày về", required=True)
    bill_number = fields.Char(string="Vận đơn")
    line_ids = fields.One2many("contract.arrival.line", "arrival_id", string="Chi tiết lần về", copy=False)
    qty_planned_total = fields.Float(
        string="Tổng SL kế hoạch",
        compute="_compute_qty_totals",
        digits="Product Unit of Measure",
    )
    qty_received_total = fields.Float(
        string="Tổng SL đã nhận",
        compute="_compute_qty_totals",
        digits="Product Unit of Measure",
    )

    _sql_constraints = [
        (
            "contract_delivery_schedule_unique",
            "unique(contract_id, delivery_schedule_id)",
            "Mỗi lịch giao chỉ tạo một lần về cho từng hợp đồng.",
        ),
    ]

    @api.depends("line_ids.qty_planned", "line_ids.qty_received")
    def _compute_qty_totals(self):
        for rec in self:
            rec.qty_planned_total = sum(rec.line_ids.mapped("qty_planned"))
            rec.qty_received_total = sum(rec.line_ids.mapped("qty_received"))

    def action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lần về"),
            "res_model": "contract.arrival",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class ContractArrivalLine(models.Model):
    _name = "contract.arrival.line"
    _description = "Chi tiết sản phẩm lần về hợp đồng"
    _order = "id"

    arrival_id = fields.Many2one("contract.arrival", string="Lần về", required=True, ondelete="cascade", index=True)
    contract_id = fields.Many2one(related="arrival_id.contract_id", store=True, readonly=True)
    delivery_schedule_allocation_id = fields.Many2one(
        "delivery.schedule.allocation",
        string="Dòng phân bổ lịch giao",
        required=True,
        ondelete="cascade",
        index=True,
    )
    purchase_line_id = fields.Many2one(related="delivery_schedule_allocation_id.purchase_line_id", store=True, readonly=True)
    purchase_id = fields.Many2one(related="delivery_schedule_allocation_id.purchase_id", store=True, readonly=True)
    product_id = fields.Many2one(related="delivery_schedule_allocation_id.product_id", store=True, readonly=True)
    uom_id = fields.Many2one(related="delivery_schedule_allocation_id.uom_id", store=True, readonly=True)
    qty_planned = fields.Float(
        related="delivery_schedule_allocation_id.qty_planned",
        string="SL kế hoạch",
        readonly=True,
        digits="Product Unit of Measure",
    )
    qty_received = fields.Float(
        related="delivery_schedule_allocation_id.qty_received",
        string="SL đã nhận",
        readonly=True,
        digits="Product Unit of Measure",
    )

    _sql_constraints = [
        (
            "arrival_allocation_unique",
            "unique(arrival_id, delivery_schedule_allocation_id)",
            "Dòng phân bổ đã tồn tại trong lần về này.",
        ),
    ]

