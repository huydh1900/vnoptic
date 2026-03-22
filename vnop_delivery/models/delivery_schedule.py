from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class DeliverySchedule(models.Model):
    _name = 'delivery.schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'delivery_datetime desc, id desc'
    _rec_name = 'name'
    _description = 'Lịch giao hàng'

    name = fields.Char(string='Đợt giao', default=lambda self: _('Mới'), copy=False, required=True)
    delivery_datetime = fields.Date(
        string='Thời gian giao hàng',
        required=True,
        tracking=True
    )

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

    purchase_id = fields.Many2one(
        'purchase.order',
        string='Đơn mua hàng',
        readonly=True,
        copy=False,
    )
    contract_id = fields.Many2one('contract', string='Hợp đồng', index=True, tracking=True, required=True)
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company, required=True)

    picking_ids = fields.One2many('stock.picking', 'delivery_schedule_id', string='Phiếu nhập kho', readonly=True)

    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    insurance_fee = fields.Monetary(string='Phí bảo hiểm', currency_field='currency_id', default=0)
    environment_fee = fields.Monetary(string='Phí môi trường', currency_field='currency_id', default=0)
    total_declaration_amount = fields.Monetary(string='Tổng giá trị theo tờ khai', currency_field='currency_id', default=0)

    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Xác nhận hàng về'),
    ], default='draft', string='Trạng thái', tracking=True)

    picking_count = fields.Integer(compute='_compute_picking_count')
    otk_session_count = fields.Integer(compute='_compute_otk_session_count', string='Số lần OTK')
    purchase_count = fields.Integer(compute='_compute_purchase_count')
    color = fields.Integer(string="Màu", compute="_compute_color", store=True)

    @api.depends('state')
    def _compute_color(self):
        mapping = {'draft': 1, 'confirmed': 10}
        for rec in self:
            rec.color = mapping.get(rec.state, 0)

    @api.depends('picking_ids', 'picking_ids.delivery_otk_id')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    def _compute_purchase_count(self):
        for rec in self:
            rec.purchase_count = 1 if rec.purchase_id else 0

    def _compute_otk_session_count(self):
        grouped = self.env['delivery.otk'].read_group(
            [('delivery_schedule_id', 'in', self.ids)],
            ['delivery_schedule_id'],
            ['delivery_schedule_id'],
            lazy=False,
        )
        count_map = {
            item['delivery_schedule_id'][0]: item.get('delivery_schedule_id_count', item.get('__count', 0))
            for item in grouped if item.get('delivery_schedule_id')
        }
        for rec in self:
            rec.otk_session_count = count_map.get(rec.id, 0)

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
            po = rec._auto_create_po_from_offer_remaining()
            if po:
                po.button_confirm()
                rec.purchase_id = po

    def _auto_create_po_from_offer_remaining(self):
        self.ensure_one()
        contract = self.contract_id
        if not contract:
            return

        offer_lines = contract.purchase_offer_ids.mapped('line_ids')
        if not offer_lines:
            return

        existing_po_lines = self.env['purchase.order.line'].search([
            ('order_id.contract_id', '=', contract.id),
            ('display_type', '=', False),
        ])
        qty_in_po = {}
        for pol in existing_po_lines:
            key = (pol.product_id.id, pol.product_uom.id)
            qty_in_po[key] = qty_in_po.get(key, 0.0) + pol.product_qty

        lines_to_create = []
        for offer_line in offer_lines:
            key = (offer_line.product_id.id, offer_line.uom_id.id)
            qty_remaining = offer_line.quantity - qty_in_po.get(key, 0.0)
            if qty_remaining <= 0:
                continue
            lines_to_create.append({
                'product_id': offer_line.product_id.id,
                'product_uom': offer_line.uom_id.id,
                'product_qty': qty_remaining,
                'price_unit': offer_line.expected_price,
                'name': offer_line.product_id.display_name,
                'date_planned': self.delivery_datetime or fields.Date.context_today(self),
            })

        if not lines_to_create:
            return

        po = self.env['purchase.order'].create({
            'name': self.env['ir.sequence'].next_by_code('purchase.order') or '/',
            'partner_id': contract.partner_id.id,
            'partner_ref': contract.partner_id.ref or False,
            'company_id': contract.company_id.id,
            'currency_id': contract.currency_id.id,
            'contract_id': contract.id,
            'order_line': [(0, 0, vals) for vals in lines_to_create],
        })
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

    def action_view_otk_sessions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lần OTK'),
            'res_model': 'delivery.otk',
            'view_mode': 'list,form',
            'domain': [('delivery_schedule_id', '=', self.id)],
            'target': 'current',
        }

    def action_create_otk_sessions(self, raise_if_empty=True, return_action=True):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Chỉ tạo OTK khi lịch giao ở trạng thái Xác nhận hàng về.'))
        if not self.contract_id:
            raise UserError(_('Lịch giao chưa có hợp đồng liên quan.'))

        received_map = self._get_received_qty_by_purchase_line()
        contract = self.contract_id
        source, ok_location, ng_location, picking_type = self._get_default_otk_configuration()
        if not source or not ok_location or not ng_location or not picking_type:
            raise UserError(_('Thiếu cấu hình OTK mặc định của công ty.'))

        line_values = []
        for po in self.purchase_id:
            for po_line in po.order_line.filtered(lambda l: not l.display_type and l.product_id):
                qty_received = received_map.get(po_line.id, 0.0)
                qty_done_otk = self._get_otk_checked_qty(
                    contract_id=contract.id,
                    purchase_line_id=po_line.id,
                )
                qty_to_otk = max(qty_received - qty_done_otk, 0.0)
                if qty_to_otk <= 0:
                    continue
                line_values.append((0, 0, {
                    'purchase_line_id': po_line.id,
                    'qty_contract': qty_to_otk,
                }))

        if not line_values:
            if raise_if_empty:
                raise UserError(_('Không có số lượng đã nhận để tạo phiên OTK.'))
            return False

        session = self.env['delivery.otk'].create({
            'contract_id': contract.id,
            'company_id': self.company_id.id,
            'source_location_id': source.id,
            'ok_location_id': ok_location.id,
            'ng_location_id': ng_location.id,
            'picking_type_id': picking_type.id,
            'delivery_schedule_id': self.id,
            'line_ids': line_values,
        })

        if not return_action:
            return session

        return {
            'type': 'ir.actions.act_window',
            'name': _('Lần OTK'),
            'res_model': 'delivery.otk',
            'view_mode': 'list,form',
            'domain': [('id', 'in', session.ids)],
            'target': 'current',
        }

    def _get_otk_checked_qty(self, contract_id, purchase_line_id):
        self.ensure_one()
        rows = self.env['delivery.otk.line'].read_group(
            [
                ('otk_id.delivery_schedule_id', '=', self.id),
                ('otk_id.contract_id', '=', contract_id),
                ('otk_id.state', 'in', ('confirmed', 'done')),
                ('purchase_line_id', '=', purchase_line_id),
            ],
            ['qty_checked:sum'],
            [],
            lazy=False,
        )
        return (rows[0].get('qty_checked', 0.0) or 0.0) if rows else 0.0

    def _get_default_otk_configuration(self):
        self.ensure_one()
        company = self.company_id
        source = company.otk_source_location_id
        internal_picking_type = company.otk_internal_picking_type_id
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        main_location = warehouse.lot_stock_id

        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("company_id", "=", company.id),
        ], limit=1)
        source = source or incoming_type.default_location_dest_id
        if not main_location:
            raise UserError(_("Không tìm thấy Kho chính WH/Stock để tạo OTK."))

        internal_picking_type = internal_picking_type or self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("company_id", "=", company.id),
        ], limit=1)
        return source, main_location, company.otk_ng_location_id, internal_picking_type

    def _get_received_qty_by_purchase_line(self):
        self.ensure_one()
        move_lines = self.env['stock.move.line']
        done_field = 'qty_done' if 'qty_done' in move_lines._fields else 'quantity'
        rows = move_lines.search([
            ('move_id.delivery_schedule_id', '=', self.id),
            ('move_id.purchase_line_id', '!=', False),
            ('move_id.state', '=', 'done'),
            ('move_id.picking_id.picking_type_code', '=', 'incoming'),
        ])
        result = {}
        for row in rows:
            line_id = row.move_id.purchase_line_id.id
            result[line_id] = result.get(line_id, 0.0) + (row[done_field] or 0.0)
        return result

    def _sync_state_from_receipts(self):
        for rec in self:
            if rec.state == 'draft' and rec._get_received_qty_by_purchase_line():
                rec.state = 'confirmed'
