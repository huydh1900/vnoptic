from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class DeliverySchedule(models.Model):
    _name = 'delivery.schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'delivery_datetime desc, id desc'
    _rec_name = 'name'
    _description = 'Lịch giao hàng'

    name = fields.Char(string='Đợt giao', default=lambda self: _('Mới'), copy=False, required=True)
    delivery_datetime = fields.Date(string='Thời gian giao hàng', required=True, tracking=True)

    declaration_date = fields.Date(string='Ngày tờ khai')
    declaration_number = fields.Char(string='Số tờ khai')
    bill_number = fields.Char(string='Mã vận đơn')
    description = fields.Text(string='Mô tả')

    eta = fields.Date(string='ETA (Ngày dự kiến đến)', tracking=True)
    etd = fields.Date(string='ETD (Ngày dự kiến khởi hành)', tracking=True)
    shipment_type = fields.Selection([
        ('air', 'Đường hàng không'),
        ('sea', 'Đường biển'),
        ('land', 'Đường bộ'),
    ], string='Phương thức vận chuyển', tracking=True)

    incoterm_id = fields.Many2one('account.incoterms', string='Điều kiện giao hàng', tracking=True)
    port_loading = fields.Char(string='Cảng xuất hàng')
    port_discharge = fields.Char(string='Cảng đích')

    freight_est = fields.Monetary(string='Cước vận chuyển (dự tính)', currency_field='currency_id', default=0)
    insurance_est = fields.Monetary(string='Phí bảo hiểm (dự tính)', currency_field='currency_id', default=0)
    duty_est = fields.Monetary(string='Thuế nhập khẩu (dự tính)', currency_field='currency_id', default=0)
    tax_est = fields.Monetary(string='Thuế VAT (dự tính)', currency_field='currency_id', default=0)
    other_cost_est = fields.Monetary(string='Chi phí khác (dự tính)', currency_field='currency_id', default=0)

    partner_id = fields.Many2one('res.partner', string='Nhà cung cấp', required=True)
    partner_ref = fields.Char(string='Mã NCC', related='partner_id.ref')

    purchase_id = fields.Many2one('purchase.order', string='Đơn mua hàng', readonly=True, copy=False)
    contract_id = fields.Many2one('contract', string='Hợp đồng', index=True, tracking=True, required=True)
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    picking_ids = fields.One2many('stock.picking', 'delivery_schedule_id', string='Phiếu nhập kho', readonly=True)
    line_ids = fields.One2many('delivery.schedule.line', 'schedule_id', string='Chi tiết hàng giao')

    insurance_fee = fields.Monetary(string='Phí bảo hiểm', currency_field='currency_id', default=0)
    environment_fee = fields.Monetary(string='Phí môi trường', currency_field='currency_id', default=0)
    total_declaration_amount = fields.Monetary(string='Tổng giá trị theo tờ khai', currency_field='currency_id', default=0)

    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Xác nhận hàng về'),
    ], default='draft', string='Trạng thái', tracking=True)

    picking_count = fields.Integer(compute='_compute_picking_count')
    purchase_count = fields.Integer(compute='_compute_purchase_count')
    color = fields.Integer(string="Màu", compute="_compute_color", store=True)

    @api.depends('state')
    def _compute_color(self):
        mapping = {'draft': 1, 'confirmed': 10}
        for rec in self:
            rec.color = mapping.get(rec.state, 0)

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    def _compute_purchase_count(self):
        for rec in self:
            rec.purchase_count = 1 if rec.purchase_id else 0

    def _check_can_move_state(self):
        for rec in self:
            if not rec.contract_id:
                raise ValidationError(_('Bạn cần chọn hợp đồng cho lịch giao.'))
            if not rec.partner_id:
                raise ValidationError(_('Bạn cần chọn nhà cung cấp cho lịch giao.'))

    def action_confirmed(self):
        self._check_can_move_state()
        self.write({'state': 'confirmed'})
        for rec in self:
            po = rec._create_po_from_schedule_lines()
            if po:
                po.button_confirm()
                rec.purchase_id = po

    def _create_po_from_schedule_lines(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.qty_planned > 0)
        if not lines:
            return

        contract = self.contract_id
        po = self.env['purchase.order'].create({
            'partner_id': contract.partner_id.id,
            'partner_ref': contract.partner_id.ref or False,
            'company_id': contract.company_id.id,
            'currency_id': contract.currency_id.id,
            'contract_id': contract.id,
        })
        planned_date = self.delivery_datetime or fields.Date.context_today(self)
        for line in lines:
            purchase_line = self.env['purchase.order.line'].create({
                'order_id': po.id,
                'product_id': line.product_id.id,
                'product_uom': line.uom_id.id,
                'product_qty': line.qty_planned,
                'price_unit': line.price_unit,
                'name': line.product_id.display_name,
                'date_planned': planned_date,
            })
            line.contract_line_id.purchase_line_id = purchase_line.id
        return po

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        for rec in self:
            if not rec.contract_id:
                continue
            rec.partner_id = rec.contract_id.partner_id
            rec.company_id = rec.contract_id.company_id
            rec.currency_id = rec.contract_id.currency_id
            rec.incoterm_id = rec.contract_id.incoterm_id
            rec.port_loading = rec.contract_id.port_of_loading
            rec.port_discharge = rec.contract_id.destination
            rec.line_ids = [(5, 0, 0)] + [(0, 0, {
                'contract_line_id': line.id,
                'qty_planned': line.product_qty,
            }) for line in rec.contract_id.line_ids]

    def action_view_contract(self):
        self.ensure_one()
        if not self.contract_id:
            raise UserError(_('Lịch giao chưa có hợp đồng liên quan.'))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Hợp đồng mua hàng',
            'res_model': 'contract',
            'view_mode': 'form',
            'res_id': self.contract_id.id,
            'target': 'current',
        }

    def action_view_purchase_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Đơn mua hàng'),
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_id.id,
            'target': 'current',
        }

    def _sync_state_from_receipts(self):
        for rec in self:
            if rec.state == 'draft':
                move_lines = self.env['stock.move.line']
                done_field = 'qty_done' if 'qty_done' in move_lines._fields else 'quantity'
                rows = move_lines.search([
                    ('move_id.delivery_schedule_id', '=', rec.id),
                    ('move_id.state', '=', 'done'),
                    ('move_id.picking_id.picking_type_code', '=', 'incoming'),
                ])
                if any(row[done_field] > 0 for row in rows):
                    rec.state = 'confirmed'
