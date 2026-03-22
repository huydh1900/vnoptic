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

    declaration_date = fields.Date(
        string='Ngày tờ khai'
    )

    declaration_number = fields.Char(
        string='Số tờ khai'
    )

    bill_number = fields.Char(
        string='Mã vận đơn'
    )
    description = fields.Text(
        string='Mô tả'
    )

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

    allocation_ids = fields.One2many(
        'delivery.schedule.allocation',
        'schedule_id',
        string='Chi tiết hàng giao',
        copy=True,
    )
    purchase_ids = fields.Many2many(
        'purchase.order',
        'delivery_schedule_purchase_rel',
        'schedule_id',
        'purchase_id',
        string='Đơn mua hàng',
    )
    contract_id = fields.Many2one(
        'contract',
        string='Hợp đồng',
        index=True,
        tracking=True,
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Công ty',
        default=lambda self: self.env.company,
        required=True
    )

    picking_ids = fields.One2many(
        'stock.picking',
        'delivery_schedule_id',
        string='Phiếu nhập kho',
        readonly=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )

    insurance_fee = fields.Monetary(
        string='Phí bảo hiểm',
        currency_field='currency_id',
        default=0
    )

    environment_fee = fields.Monetary(
        string='Phí môi trường',
        currency_field='currency_id',
        default=0
    )

    total_declaration_amount = fields.Monetary(
        string='Tổng giá trị theo tờ khai',
        currency_field='currency_id',
        default=0
    )

    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Xác nhận hàng về'),
    ], default='draft', string='Trạng thái', tracking=True)

    picking_count = fields.Integer(compute='_compute_picking_count')
    otk_session_count = fields.Integer(compute='_compute_otk_session_count', string='Số lần OTK')
    qty_planned_total = fields.Float(
        string='SL kế hoạch',
        compute='_compute_qty_totals',
        digits='Product Unit of Measure',
    )
    qty_received_total = fields.Float(
        string='SL đã nhận',
        compute='_compute_qty_totals',
        digits='Product Unit of Measure',
    )

    color = fields.Integer(string="Màu", compute="_compute_color", store=True)

    @api.depends('state')
    def _compute_color(self):
        mapping = {
            'draft': 1,
            'confirmed': 10,
        }
        for rec in self:
            rec.color = mapping.get(rec.state, 0)

    @api.depends('picking_ids', 'picking_ids.delivery_otk_id')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    @api.depends('allocation_ids.qty_planned', 'allocation_ids.qty_received')
    def _compute_qty_totals(self):
        for rec in self:
            rec.qty_planned_total = sum(rec.allocation_ids.mapped('qty_planned'))
            rec.qty_received_total = sum(rec.allocation_ids.mapped('qty_received'))

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
            if not rec.purchase_ids:
                raise ValidationError(_('Bạn cần chọn ít nhất một đơn mua hàng cho lịch giao.'))
            if not rec.allocation_ids:
                raise ValidationError(_('Bạn cần ít nhất một dòng phân bổ PO/SKU.'))

    def action_confirmed(self):
        self._check_can_move_state()
        self.write({'state': 'confirmed'})
        for rec in self:
            rec._sync_contract_arrivals()

    def action_create_receipt(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Chỉ tạo phiếu nhập khi lịch giao ở trạng thái Xác nhận hàng về.'))
        if not self.allocation_ids:
            raise UserError(_('Lịch giao chưa có dòng phân bổ để tạo phiếu nhập kho.'))

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming')
        ], order='id', limit=1)

        if not picking_type:
            raise UserError(_("Chưa cấu hình loại vận chuyển nhập kho (incoming)."))

        lines_to_receive = self.allocation_ids.filtered(lambda l: l.qty_remaining_to_receive > 0)
        if not lines_to_receive:
            raise UserError(_('Toàn bộ số lượng của lịch giao đã nhận xong.'))

        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'picking_type_id': picking_type.id,
            'origin': self.bill_number,
            'scheduled_date': self.delivery_datetime,
            'company_id': self.company_id.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
            'delivery_schedule_id': self.id,
        })

        for line in lines_to_receive:
            uom_id = line.uom_id.id or line.product_id.uom_po_id.id or line.product_id.uom_id.id
            self.env['stock.move'].create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': uom_id,
                'product_uom_qty': line.qty_remaining_to_receive,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'purchase_line_id': line.purchase_line_id.id,
                'delivery_schedule_id': self.id,
                'delivery_schedule_allocation_id': line.id,
                'contract_id': line.contract_id.id,
            })

        picking.action_confirm()
        self._sync_state_from_receipts()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
        }

    @api.onchange('purchase_ids')
    def _onchange_purchase_ids(self):
        for rec in self:
            if not rec.purchase_ids:
                rec.allocation_ids = [(5, 0, 0)]
                continue
            missing_contract_po = rec.purchase_ids.filtered(lambda po: not po.contract_id)
            if missing_contract_po:
                rec.purchase_ids = rec.purchase_ids - missing_contract_po
                names = ", ".join(missing_contract_po.mapped("name"))
                return {
                    "warning": {
                        "title": _("Thiếu hợp đồng trên đơn mua"),
                        "message": _(
                            "Không thể thêm các đơn mua chưa liên kết hợp đồng: %s.\n"
                            "Vui lòng gán hợp đồng cho PO trước khi đưa vào lịch giao."
                        ) % names,
                    }
                }
            partner = rec.purchase_ids[:1].partner_id
            if partner:
                rec.partner_id = partner
            purchase_contracts = rec.purchase_ids.mapped("contract_id")
            if len(purchase_contracts) == 1:
                rec.contract_id = purchase_contracts.id
            rec.allocation_ids = rec._build_allocation_commands_from_purchase_ids()

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
            rec.purchase_ids = rec.purchase_ids.filtered(lambda po: po.contract_id == rec.contract_id)
            rec.allocation_ids = rec._build_allocation_commands_from_purchase_ids()

    def _build_allocation_commands_from_purchase_ids(self):
        self.ensure_one()
        missing_contract_po = self.purchase_ids.filtered(lambda po: not po.contract_id)
        if missing_contract_po:
            names = ", ".join(missing_contract_po.mapped("name"))
            raise ValidationError(
                _('Các đơn mua sau chưa liên kết hợp đồng: %s. Vui lòng gán hợp đồng trước khi lập lịch giao.')
                % names
            )
        existing = {
            line.purchase_line_id.id: line
            for line in self.allocation_ids.filtered('purchase_line_id')
        }
        commands = [(5, 0, 0)]
        for order in self.purchase_ids:
            default_contract = order.contract_id
            for po_line in order.order_line.filtered(lambda l: not l.display_type and l.product_id):
                qty_planned = max(po_line.qty_remaining, 0.0)
                if qty_planned <= 0:
                    continue
                old = existing.get(po_line.id)
                commands.append((0, 0, {
                    'purchase_line_id': po_line.id,
                    'contract_id': old.contract_id.id if old and old.contract_id == order.contract_id else (default_contract.id or False),
                    'qty_planned': old.qty_planned if old else qty_planned,
                }))
        return commands

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

    def action_view_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Phiếu nhập kho',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('delivery_schedule_id', '=', self.id)],
            'context': {'default_delivery_schedule_id': self.id},
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

        sessions = self.env['delivery.otk']
        received_map = self._get_received_qty_by_purchase_line()
        contract = self.contract_id
        source, ok_location, ng_location, picking_type = self._get_default_otk_configuration()
        if not source or not ok_location or not ng_location or not picking_type:
            raise UserError(
                _('Thiếu cấu hình OTK mặc định của công ty.')
            )

        line_values = []
        for alloc in self.allocation_ids:
            qty_received = received_map.get(alloc.purchase_line_id.id, 0.0)
            qty_done_otk = self._get_otk_checked_qty(
                contract_id=contract.id,
                purchase_line_id=alloc.purchase_line_id.id,
            )
            qty_to_otk = max(qty_received - qty_done_otk, 0.0)
            if qty_to_otk <= 0:
                continue
            line_values.append((0, 0, {
                'purchase_line_id': alloc.purchase_line_id.id,
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
        sessions |= session

        if not return_action:
            return sessions

        return {
            'type': 'ir.actions.act_window',
            'name': _('Lần OTK'),
            'res_model': 'delivery.otk',
            'view_mode': 'list,form',
            'domain': [('id', 'in', sessions.ids)],
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
        if not rows:
            return 0.0
        return rows[0].get('qty_checked', 0.0) or 0.0

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
            if not rec.allocation_ids:
                continue
            if rec.state == 'draft' and any(line.qty_received > 0 for line in rec.allocation_ids):
                rec.state = 'confirmed'

    def _sync_contract_arrivals(self):
        self.ensure_one()
        if not self.contract_id:
            return
        Arrival = self.env["contract.arrival"]
        contract = self.contract_id
        arrival = Arrival.search([
            ("contract_id", "=", contract.id),
            ("delivery_schedule_id", "=", self.id),
        ], limit=1)
        contract_allocations = self.allocation_ids.filtered(lambda line: line.qty_planned > 0)
        if not contract_allocations:
            if arrival:
                arrival.unlink()
            return
        line_commands = [(5, 0, 0)] + [
            (0, 0, {"delivery_schedule_allocation_id": allocation.id})
            for allocation in contract_allocations
        ]
        arrival_vals = {
            "name": "%s - %s" % (self.bill_number or self.name, contract.number or contract.name),
            "contract_id": contract.id,
            "delivery_schedule_id": self.id,
            "arrival_date": self.delivery_datetime or fields.Date.context_today(self),
            "bill_number": self.bill_number,
            "line_ids": line_commands,
        }
        if arrival:
            arrival.write(arrival_vals)
        else:
            Arrival.create(arrival_vals)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for rec in self:
            if not rec.partner_id:
                continue
            rec.purchase_ids = rec.purchase_ids.filtered(lambda po: po.partner_id == rec.partner_id)
            rec.allocation_ids = rec._build_allocation_commands_from_purchase_ids()

    @api.constrains('purchase_ids', 'partner_id')
    def _check_purchase_partner(self):
        for rec in self:
            if not rec.purchase_ids or not rec.partner_id:
                continue
            invalid_pos = rec.purchase_ids.filtered(lambda po: po.partner_id != rec.partner_id)
            if invalid_pos:
                raise ValidationError(_('Tất cả đơn mua trong lịch giao phải cùng nhà cung cấp.'))

    @api.constrains('purchase_ids')
    def _check_purchase_has_contract(self):
        for rec in self:
            if not rec.purchase_ids:
                continue
            missing_contract_po = rec.purchase_ids.filtered(lambda po: not po.contract_id)
            if missing_contract_po:
                names = ", ".join(missing_contract_po.mapped("name"))
                raise ValidationError(
                    _('Các đơn mua sau chưa liên kết hợp đồng: %s. Vui lòng gán hợp đồng trước khi lưu lịch giao.')
                    % names
                )
