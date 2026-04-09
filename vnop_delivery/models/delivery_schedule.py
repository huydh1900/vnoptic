from collections import defaultdict

from odoo import api, fields, models, _
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
    extra_cost_line_ids = fields.One2many(
        'delivery.schedule.extra.cost.line',
        'schedule_id',
        string='Phí bổ sung',
    )
    landed_cost_ids = fields.One2many(
        'stock.landed.cost',
        'delivery_schedule_id',
        string='Chi phí phân bổ',
        readonly=True,
    )

    insurance_fee = fields.Monetary(string='Phí bảo hiểm', currency_field='currency_id', default=0)
    environment_fee = fields.Monetary(string='Phí môi trường', currency_field='currency_id', default=0)
    total_declaration_amount = fields.Monetary(string='Tổng giá trị theo tờ khai', currency_field='currency_id', default=0)

    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Xác nhận hàng về'),
    ], default='draft', string='Trạng thái', tracking=True)

    picking_count = fields.Integer(compute='_compute_picking_count')
    purchase_count = fields.Integer(string='Đơn mua hàng', compute='_compute_purchase_count')
    color = fields.Integer(string="Màu", compute="_compute_color", store=True)
    provisional_landed_cost_total = fields.Monetary(
        string='LC tạm tính đã hạch toán',
        currency_field='currency_id',
        compute='_compute_landed_cost_totals',
    )
    final_landed_cost_total = fields.Monetary(
        string='LC điều chỉnh chốt',
        currency_field='currency_id',
        compute='_compute_landed_cost_totals',
    )

    @api.depends('state')
    def _compute_color(self):
        mapping = {'draft': 1, 'confirmed': 10}
        for rec in self:
            rec.color = mapping.get(rec.state, 0)

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    @api.depends('purchase_id')
    def _compute_purchase_count(self):
        for rec in self:
            rec.purchase_count = 1 if rec.purchase_id else 0

    @api.depends('landed_cost_ids.state', 'landed_cost_ids.amount_total', 'landed_cost_ids.is_provisional',
                 'landed_cost_ids.is_final_adjustment')
    def _compute_landed_cost_totals(self):
        for rec in self:
            posted_costs = rec.landed_cost_ids.filtered(lambda c: c.state == 'done')
            rec.provisional_landed_cost_total = sum(
                posted_costs.filtered('is_provisional').mapped('amount_total')
            )
            rec.final_landed_cost_total = sum(
                posted_costs.filtered('is_final_adjustment').mapped('amount_total')
            )

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
                po.picking_ids.write({'delivery_schedule_id': rec.id})

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

            # Tính SL đã lên lịch từ các lần trước
            existing = self.env['delivery.schedule'].search([
                ('contract_id', '=', rec.contract_id.id),
                ('id', '!=', rec._origin.id or 0),
            ])
            planned_by_cl = {}
            for l in existing.mapped('line_ids'):
                cl_id = l.contract_line_id.id
                planned_by_cl[cl_id] = planned_by_cl.get(cl_id, 0) + l.qty_planned

            rec.line_ids = [(5, 0, 0)] + [(0, 0, {
                'contract_line_id': line.id,
                'qty_planned': max(line.product_qty - planned_by_cl.get(line.id, 0), 0),
            }) for line in rec.contract_id.line_ids
                if planned_by_cl.get(line.id, 0) < line.product_qty]

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

    # -------------------------------------------------------------------------
    # Chi phí phân bổ: tạm tính theo OTK + điều chỉnh chốt
    # -------------------------------------------------------------------------

    def _find_landed_cost_product(self, preferred_codes):
        Product = self.env['product.product']
        for code in preferred_codes:
            product = Product.search([
                ('default_code', '=', code),
                ('landed_cost_ok', '=', True),
            ], limit=1)
            if product:
                return product
        return Product

    def _prepare_standard_cost_buckets(self):
        self.ensure_one()
        configs = [
            ('freight', 'freight_est', ['LC-VCQT', 'LC-VCND'], 'by_current_cost_price', 'Cước vận chuyển'),
            ('insurance', 'insurance_est', ['LC-BH'], 'by_current_cost_price', 'Phí bảo hiểm'),
            ('duty', 'duty_est', ['LC-TNK'], 'by_current_cost_price', 'Thuế nhập khẩu'),
            ('tax', 'tax_est', ['LC-VAT'], 'by_current_cost_price', 'Thuế VAT'),
            ('other', 'other_cost_est', ['LC-PSK'], 'by_current_cost_price', 'Chi phí khác'),
        ]
        buckets = []
        for key, field_name, codes, fallback_split, label in configs:
            amount = getattr(self, field_name, 0.0) or 0.0
            if self.currency_id.is_zero(amount):
                continue
            product = self._find_landed_cost_product(codes)
            if not product:
                continue
            buckets.append({
                'key': key,
                'name': label,
                'amount': amount,
                'product': product,
                'split_method': product.product_tmpl_id.split_method_landed_cost or fallback_split,
            })
        return buckets

    @staticmethod
    def _standard_cost_key_from_default_code(default_code):
        mapping = {
            'LC-VCQT': 'freight',
            'LC-VCND': 'freight',
            'LC-BH': 'insurance',
            'LC-TNK': 'duty',
            'LC-VAT': 'tax',
            'LC-PSK': 'other',
        }
        return mapping.get(default_code or '')

    def _prepare_actual_cost_buckets(self):
        self.ensure_one()
        # Mặc định giữ nguyên dự tính; user override thực tế qua extra_cost_line_ids.
        buckets_by_key = {bucket['key']: dict(bucket) for bucket in self._prepare_standard_cost_buckets()}
        for line in self.extra_cost_line_ids:
            amount = line.amount or 0.0
            if self.currency_id.is_zero(amount):
                continue
            key = self._standard_cost_key_from_default_code(line.product_id.default_code) or f'extra:{line.id}'
            buckets_by_key[key] = {
                'key': key,
                'name': line.product_id.display_name,
                'amount': amount,
                'product': line.product_id,
                'split_method': line.split_method or line.product_id.product_tmpl_id.split_method_landed_cost or 'equal',
            }
        return list(buckets_by_key.values())

    def _prepare_landed_cost_line_vals(self, bucket, amount):
        product = bucket['product']
        accounts = product.product_tmpl_id.get_product_accounts()
        return {
            'name': bucket['name'],
            'product_id': product.id,
            'price_unit': amount,
            'split_method': bucket['split_method'],
            'account_id': accounts.get('stock_input').id if accounts.get('stock_input') else False,
            'cost_key': bucket['key'],
        }

    def _get_done_incoming_pickings(self):
        self.ensure_one()
        return self.picking_ids.filtered(lambda p: p.state == 'done' and p.picking_type_code == 'incoming')

    def _get_total_planned_qty(self):
        self.ensure_one()
        return sum(self.line_ids.mapped('qty_planned'))

    def _get_cumulative_ok_qty(self):
        self.ensure_one()
        logs = self.env['stock.otk.log'].search([
            ('picking_id.delivery_schedule_id', '=', self.id),
        ])
        return sum(logs.mapped('line_ids').filtered(lambda l: not l.is_extra).mapped('qty_ok'))

    def _get_provisional_allocated_by_key(self):
        self.ensure_one()
        allocated = defaultdict(float)
        costs = self.landed_cost_ids.filtered(lambda c: c.is_provisional and c.state != 'cancel')
        for cost in costs:
            for line in cost.cost_lines:
                if line.cost_key:
                    allocated[line.cost_key] += line.price_unit
        return allocated

    def _build_provisional_cost_lines(self):
        self.ensure_one()
        planned_qty = self._get_total_planned_qty()
        if planned_qty <= 0:
            return []

        cumulative_ok_qty = min(self._get_cumulative_ok_qty(), planned_qty)
        ratio = cumulative_ok_qty / planned_qty if planned_qty else 0.0
        if ratio <= 0:
            return []

        allocated_by_key = self._get_provisional_allocated_by_key()
        cost_lines = []
        for bucket in self._prepare_standard_cost_buckets():
            target_amount = self.currency_id.round(bucket['amount'] * ratio)
            delta = self.currency_id.round(target_amount - allocated_by_key.get(bucket['key'], 0.0))
            if self.currency_id.is_zero(delta):
                continue
            cost_lines.append((0, 0, self._prepare_landed_cost_line_vals(bucket, delta)))
        return cost_lines

    def _create_and_validate_landed_cost(self, *, picking_ids, cost_lines, description, is_provisional=False,
                                         is_final_adjustment=False, otk_log=False, target_moves=False):
        self.ensure_one()
        if not cost_lines:
            return self.env['stock.landed.cost']
        if not picking_ids:
            return self.env['stock.landed.cost']

        vals = {
            'target_model': 'picking',
            'picking_ids': [(6, 0, picking_ids.ids)],
            'cost_lines': cost_lines,
            'delivery_schedule_id': self.id,
            'otk_log_id': otk_log.id if otk_log else False,
            'is_provisional': is_provisional,
            'is_final_adjustment': is_final_adjustment,
            'description': description,
        }
        if target_moves:
            vals['otk_target_move_ids'] = [(6, 0, target_moves.ids)]
        landed_cost = self.env['stock.landed.cost'].create(vals)
        landed_cost.compute_landed_cost()
        landed_cost.button_validate()
        return landed_cost

    def create_provisional_landed_cost_from_otk(self, otk_log):
        self.ensure_one()
        if not otk_log or not otk_log.picking_id:
            return self.env['stock.landed.cost']
        if otk_log.landed_cost_id:
            return otk_log.landed_cost_id

        picking = otk_log.picking_id
        if picking.state != 'done' or picking.picking_type_code != 'incoming':
            return self.env['stock.landed.cost']

        target_product_ids = otk_log.line_ids.filtered(lambda l: l.qty_ok > 0).mapped('product_id').ids
        target_moves = picking.move_ids.filtered(
            lambda m: m.state != 'cancel'
            and m.quantity
            and m.product_id.id in target_product_ids
        )
        if not target_moves:
            return self.env['stock.landed.cost']
        cost_lines = self._build_provisional_cost_lines()
        landed_cost = self._create_and_validate_landed_cost(
            picking_ids=picking,
            cost_lines=cost_lines,
            description=_('Chi phí phân bổ tạm tính từ OTK %s') % (otk_log.name or '/'),
            is_provisional=True,
            otk_log=otk_log,
            target_moves=target_moves,
        )
        if landed_cost:
            otk_log.landed_cost_id = landed_cost
        return landed_cost

    def action_create_final_landed_cost_adjustment(self):
        self.ensure_one()
        pickings = self._get_done_incoming_pickings()
        if not pickings:
            raise UserError(_('Chưa có phiếu nhập hoàn tất để tạo landed cost điều chỉnh.'))

        est_map = {b['key']: b for b in self._prepare_standard_cost_buckets()}
        act_map = {b['key']: b for b in self._prepare_actual_cost_buckets()}
        all_keys = set(est_map) | set(act_map)
        cost_lines = []
        for key in all_keys:
            est = est_map.get(key)
            act = act_map.get(key)
            delta = (act['amount'] if act else 0.0) - (est['amount'] if est else 0.0)
            delta = self.currency_id.round(delta)
            if self.currency_id.is_zero(delta):
                continue
            bucket = act or est
            cost_lines.append((0, 0, self._prepare_landed_cost_line_vals(bucket, delta)))

        if not cost_lines:
            raise UserError(_('Không có chênh lệch giữa chi phí thực tế và dự tính để điều chỉnh.'))

        landed_cost = self._create_and_validate_landed_cost(
            picking_ids=pickings,
            cost_lines=cost_lines,
            description=_('Điều chỉnh chốt landed cost: %s') % (self.name or '/'),
            is_final_adjustment=True,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Chi phí phân bổ điều chỉnh'),
            'res_model': 'stock.landed.cost',
            'view_mode': 'form',
            'res_id': landed_cost.id,
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
                if any(getattr(row, done_field) > 0 for row in rows):
                    rec.state = 'confirmed'
