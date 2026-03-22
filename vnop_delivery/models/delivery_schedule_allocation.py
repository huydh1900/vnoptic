# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DeliveryScheduleAllocation(models.Model):
    _name = 'delivery.schedule.allocation'
    _description = 'Phân bổ PO line cho lịch giao'
    _order = 'schedule_id, id'

    schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Lịch giao',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(related='schedule_id.company_id', store=True, readonly=True)
    partner_id = fields.Many2one(related='schedule_id.partner_id', store=True, readonly=True)

    purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='Dòng PO',
        required=True,
        domain="[('display_type', '=', False), ('state', 'in', ('purchase', 'done'))]",
        index=True,
    )
    purchase_id = fields.Many2one(
        'purchase.order',
        string='Đơn mua hàng',
        related='purchase_line_id.order_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Sản phẩm',
        related='purchase_line_id.product_id',
        store=True,
        readonly=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='ĐVT',
        related='purchase_line_id.product_uom',
        store=True,
        readonly=True,
    )
    contract_id = fields.Many2one(
        'contract',
        string='Hợp đồng',
        required=True,
        index=True,
    )

    qty_po = fields.Float(
        string='SL đặt hàng',
        related='purchase_line_id.product_qty',
        readonly=True,
        digits='Product Unit of Measure',
    )
    qty_planned = fields.Float(
        string='SL giao',
        required=True,
        digits='Product Unit of Measure',
    )
    qty_received = fields.Float(
        string='SL đã nhận',
        compute='_compute_receipt_qty',
        digits='Product Unit of Measure',
    )
    qty_passed = fields.Float(
        string='OTK đạt',
        compute='_compute_otk_qty',
        digits='Product Unit of Measure',
    )
    qty_failed = fields.Float(
        string='OTK lỗi',
        compute='_compute_otk_qty',
        digits='Product Unit of Measure',
    )
    qty_remaining_to_receive = fields.Float(
        string='SL còn nhận',
        compute='_compute_receipt_qty',
        digits='Product Unit of Measure',
    )

    _sql_constraints = [
        (
            'schedule_purchase_line_uniq',
            'unique(schedule_id, purchase_line_id)',
            'Dòng PO đã tồn tại trong lịch giao này.',
        ),
    ]

    @api.onchange('purchase_line_id')
    def _onchange_purchase_line_id_set_contract(self):
        for rec in self:
            if not rec.purchase_line_id:
                rec.contract_id = rec.schedule_id.contract_id.id or False
                continue
            order_contract = rec.purchase_line_id.order_id.contract_id
            if rec.contract_id and rec.contract_id == order_contract:
                continue
            rec.contract_id = order_contract.id or rec.schedule_id.contract_id.id or False

    @api.depends('schedule_id.picking_ids.state', 'schedule_id.picking_ids.move_ids_without_package.quantity')
    def _compute_receipt_qty(self):
        data = {}
        if self.ids:
            move_lines = self.env['stock.move.line']
            done_field = 'qty_done' if 'qty_done' in move_lines._fields else 'quantity'
            rows = move_lines.search([
                ('move_id.delivery_schedule_allocation_id', 'in', self.ids),
                ('move_id.state', '=', 'done'),
                ('move_id.picking_id.picking_type_code', '=', 'incoming'),
            ])
            for row in rows:
                alloc_id = row.move_id.delivery_schedule_allocation_id.id
                data[alloc_id] = data.get(alloc_id, 0.0) + (row[done_field] or 0.0)

        for rec in self:
            rec.qty_received = data.get(rec.id, 0.0)
            rec.qty_remaining_to_receive = max((rec.qty_planned or 0.0) - rec.qty_received, 0.0)

    @api.depends('schedule_id.picking_ids.delivery_otk_id.state', 'schedule_id.picking_ids.delivery_otk_id.line_ids.qty_ok')
    def _compute_otk_qty(self):
        for rec in self:
            rec.qty_passed = 0.0
            rec.qty_failed = 0.0
            otk_lines = self.env['delivery.otk.line'].search([
                ('otk_id.delivery_schedule_id', '=', rec.schedule_id.id),
                ('otk_id.state', '=', 'done'),
                ('purchase_line_id', '=', rec.purchase_line_id.id),
            ])
            if otk_lines:
                rec.qty_passed = sum(otk_lines.mapped('qty_ok'))
                rec.qty_failed = sum(otk_lines.mapped('qty_ng'))

    @api.constrains('qty_planned', 'purchase_line_id')
    def _check_qty_planned(self):
        for rec in self:
            if rec.qty_planned <= 0:
                raise ValidationError(_('Số lượng giao phải lớn hơn 0.'))
            if rec.purchase_line_id and rec.qty_planned > rec.purchase_line_id.product_qty:
                raise ValidationError(_('Số lượng giao không được vượt quá số lượng đặt hàng.'))

    @api.constrains('schedule_id', 'purchase_line_id')
    def _check_vendor_match(self):
        for rec in self:
            if rec.schedule_id.partner_id and rec.purchase_id.partner_id != rec.schedule_id.partner_id:
                raise ValidationError(_('Nhà cung cấp của dòng PO phải trùng nhà cung cấp của lịch giao.'))
            if rec.schedule_id.purchase_ids and rec.purchase_id not in rec.schedule_id.purchase_ids:
                raise ValidationError(_('Dòng PO phải thuộc danh sách đơn mua đã chọn trong lịch giao.'))

    @api.constrains('contract_id', 'purchase_line_id')
    def _check_contract_belongs_to_purchase(self):
        for rec in self:
            if not rec.purchase_line_id or not rec.contract_id:
                continue
            if rec.contract_id != rec.purchase_line_id.order_id.contract_id:
                raise ValidationError(_('Hợp đồng phải thuộc cùng đơn mua của dòng PO đã chọn.'))

    @api.constrains('contract_id', 'schedule_id')
    def _check_contract_matches_schedule(self):
        for rec in self:
            if rec.schedule_id.contract_id and rec.contract_id and rec.schedule_id.contract_id != rec.contract_id:
                raise ValidationError(_('Dòng phân bổ phải thuộc cùng hợp đồng với lịch giao.'))


class StockMove(models.Model):
    _inherit = 'stock.move'

    delivery_schedule_id = fields.Many2one(
        'delivery.schedule',
        string='Lịch giao',
        index=True,
        copy=False,
    )
    delivery_schedule_allocation_id = fields.Many2one(
        'delivery.schedule.allocation',
        string='Phân bổ lịch giao',
        index=True,
        copy=False,
    )
