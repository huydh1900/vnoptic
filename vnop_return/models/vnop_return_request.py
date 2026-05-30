# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


STATE_SELECTION = [
    ('draft', 'Nháp'),
    ('submitted', 'Chờ duyệt nghiệp vụ'),
    ('biz_approved', 'Đã duyệt nghiệp vụ'),
    ('goods_in_transit', 'Đang vận chuyển về'),
    ('qc_checking', 'OTK kiểm hàng'),
    ('back_to_sales', 'Trả lại Sale xác minh'),
    ('qc_classified', 'OTK đã phân loại'),
    ('finance_approved', 'KT trưởng đã duyệt'),
    ('done', 'Hoàn tất'),
    ('refused', 'Từ chối'),
    ('cancel', 'Đã hủy'),
]


class VnopReturnRequest(models.Model):
    _name = 'vnop.return.request'
    _description = 'Yêu cầu trả hàng lỗi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Mã phiếu', required=True, copy=False,
                       readonly=True, default=lambda self: _('Mới'))
    state = fields.Selection(STATE_SELECTION, string='Trạng thái',
                             default='draft', tracking=True, required=True)

    # --- Thông tin chung ---
    partner_id = fields.Many2one('res.partner', string='Đại lý',
                                 required=True, tracking=True,
                                 domain="[('dealer_tier_id', '!=', False)]")
    sale_order_id = fields.Many2one(
        'sale.order', string='Đơn hàng gốc',
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['sale', 'done'])]",
        tracking=True,
        help='Chọn đơn hàng gốc để hệ thống lấy giá bán đúng lúc bán.')
    invoice_id = fields.Many2one(
        'account.move', string='Hoá đơn gốc',
        domain="[('partner_id', '=', partner_id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]",
        tracking=True)
    salesperson_id = fields.Many2one('res.users', string='Sale phụ trách',
                                     default=lambda self: self.env.user,
                                     tracking=True)
    return_type = fields.Selection(
        [('policy', 'Trả hàng theo chính sách'),
         ('exception', 'Trả hàng ngoại lệ')],
        string='Loại trả', required=True, default='policy', tracking=True)
    note = fields.Text(string='Ghi chú')
    exception_reason = fields.Text(
        string='Lý do ngoại lệ',
        help='Bắt buộc khi loại trả là Ngoại lệ hoặc khi không gắn đơn hàng gốc.')

    # --- Dòng SP ---
    line_ids = fields.One2many('vnop.return.request.line',
                               'request_id', string='Sản phẩm trả')
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company,
                                 required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    amount_total = fields.Monetary(string='Tổng tiền trả',
                                   compute='_compute_amount_total',
                                   store=True, currency_field='currency_id')

    # --- Routing approver hiện tại ---
    next_approver_role = fields.Selection(
        [('accountant', 'Kế toán'),
         ('sales_manager', 'Trưởng phòng KD'),
         ('director', 'Giám đốc'),
         ('chief_accountant', 'Kế toán trưởng'),
         ('otk', 'OTK')],
        string='Vai trò cần xử lý', compute='_compute_next_approver_role',
        store=True)

    # --- Liên kết stock & accounting ---
    return_picking_ids = fields.Many2many('stock.picking',
                                          string='Phiếu trả về kho',
                                          copy=False)
    classify_picking_ids = fields.Many2many(
        'stock.picking', 'vnop_return_classify_picking_rel',
        'request_id', 'picking_id',
        string='Phiếu phân loại nội bộ', copy=False)
    refund_move_ids = fields.Many2many('account.move',
                                       string='Hoá đơn giảm trừ', copy=False)
    return_picking_count = fields.Integer(compute='_compute_counts')
    classify_picking_count = fields.Integer(compute='_compute_counts')
    refund_move_count = fields.Integer(compute='_compute_counts')

    # --- Lệch khai báo ---
    mismatch_note = fields.Text(string='Ghi chú lệch khai báo',
                                tracking=True)

    # ======================= COMPUTE =======================
    @api.depends('line_ids.subtotal')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('subtotal'))

    @api.depends('state', 'return_type', 'amount_total', 'sale_order_id')
    def _compute_next_approver_role(self):
        threshold = self._get_director_threshold()
        for rec in self:
            role = False
            if rec.state == 'submitted':
                if rec.return_type == 'policy' and rec.sale_order_id:
                    role = 'accountant'
                elif rec.amount_total > threshold or not rec.sale_order_id:
                    role = 'director'
                else:
                    role = 'sales_manager'
            elif rec.state in ('goods_in_transit', 'qc_checking'):
                role = 'otk'
            elif rec.state == 'qc_classified':
                role = 'chief_accountant'
            rec.next_approver_role = role

    @api.depends('return_picking_ids', 'classify_picking_ids', 'refund_move_ids')
    def _compute_counts(self):
        for rec in self:
            rec.return_picking_count = len(rec.return_picking_ids)
            rec.classify_picking_count = len(rec.classify_picking_ids)
            rec.refund_move_count = len(rec.refund_move_ids)

    # ======================= ORM =======================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Mới')) == _('Mới'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'vnop.return.request') or _('Mới')
        return super().create(vals_list)

    @api.onchange('return_type')
    def _onchange_return_type(self):
        """Đổi loại trả → bỏ nhóm lỗi/lý do của line không còn thuộc loại trả."""
        if not self.return_type:
            return
        for line in self.line_ids:
            if line.defect_group and line.defect_group.return_type != self.return_type:
                line.defect_group = False
                line.reason_id = False

    @api.constrains('return_type', 'sale_order_id', 'exception_reason')
    def _check_exception_reason(self):
        for rec in self:
            if rec.return_type == 'exception' and not (rec.exception_reason or '').strip():
                raise ValidationError(_('Phải nhập "Lý do ngoại lệ" khi chọn trả hàng ngoại lệ.'))
            if not rec.sale_order_id and not (rec.exception_reason or '').strip():
                raise ValidationError(_('Không có đơn hàng gốc thì phải nhập "Lý do ngoại lệ".'))

    @api.constrains('line_ids')
    def _check_lines(self):
        for rec in self:
            if rec.state != 'draft' and not rec.line_ids:
                raise ValidationError(_('Phiếu phải có ít nhất 1 dòng sản phẩm trả.'))

    # ======================= HELPERS =======================
    @api.model
    def _get_director_threshold(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            'vnop_return.director_threshold', '10000000')
        try:
            return float(param)
        except (TypeError, ValueError):
            return 10000000.0

    def _check_role(self, role):
        mapping = {
            'accountant': 'vnop_return.group_return_accountant',
            'sales_manager': 'vnop_return.group_return_sales_manager',
            'director': 'vnop_return.group_return_director',
            'chief_accountant': 'vnop_return.group_return_chief_accountant',
            'otk': 'vnop_return.group_return_otk',
        }
        xmlid = mapping.get(role)
        if not xmlid or not self.env.user.has_group(xmlid):
            raise UserError(_('Bạn không có quyền duyệt bước này (cần vai trò: %s).',
                              dict(self._fields['next_approver_role'].selection).get(role, role)))

    def _activity_schedule_for_role(self, role, summary):
        group_xmlid = {
            'accountant': 'vnop_return.group_return_accountant',
            'sales_manager': 'vnop_return.group_return_sales_manager',
            'director': 'vnop_return.group_return_director',
            'chief_accountant': 'vnop_return.group_return_chief_accountant',
            'otk': 'vnop_return.group_return_otk',
        }.get(role)
        if not group_xmlid:
            return
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group or not group.users:
            return
        # Gán cho user đầu tiên của nhóm (có thể tự reassign sau)
        user = group.users[0]
        for rec in self:
            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=summary,
            )

    # ======================= HELPERS — WARRANTY =======================
    def _check_warranty_in_window(self):
        """Trả về list product_id (display_name) hết hạn/không có BH bán buôn.
        Chỉ áp dụng khi có sale_order_id."""
        self.ensure_one()
        if not self.sale_order_id:
            return []
        Reg = self.env['warranty.registration']
        out_of_warranty = []
        for line in self.line_ids:
            regs = Reg.search([
                ('sale_order_id', '=', self.sale_order_id.id),
                ('product_id', '=', line.product_id.id),
            ])
            # Còn BH nếu tồn tại ít nhất 1 đăng ký còn ngày BH bán buôn (>=0)
            if not regs or max(regs.mapped('days_remaining_wholesale') or [-1]) < 0:
                out_of_warranty.append(line.product_id.display_name)
        return out_of_warranty

    # ======================= ACTIONS =======================
    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Chỉ phiếu Nháp mới được gửi duyệt.'))
            if not rec.line_ids:
                raise UserError(_('Phải thêm sản phẩm trả trước khi gửi duyệt.'))
            if rec.return_type == 'policy':
                expired = rec._check_warranty_in_window()
                if expired:
                    raise UserError(_(
                        'Các sản phẩm sau đã hết hạn bảo hành bán buôn hoặc chưa có đăng ký BH: %s. '
                        'Vui lòng chọn loại "Trả hàng ngoại lệ" nếu vẫn muốn trả.',
                        ', '.join(expired),
                    ))
            rec.state = 'submitted'
            rec._activity_schedule_for_role(
                rec.next_approver_role,
                _('Duyệt yêu cầu trả hàng %s', rec.name))

    def action_biz_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Chỉ duyệt được phiếu ở trạng thái Chờ duyệt nghiệp vụ.'))
            rec._check_role(rec.next_approver_role)
            rec.activity_feedback(['mail.mail_activity_data_todo'])
            rec.state = 'biz_approved'
            rec.message_post(body=_('Đã duyệt nghiệp vụ bởi %s', self.env.user.name))

    def action_refuse(self):
        for rec in self:
            if rec.state in ('done', 'cancel', 'refused'):
                raise UserError(_('Không thể từ chối phiếu ở trạng thái hiện tại.'))
            rec.activity_feedback(['mail.mail_activity_data_todo'])
            rec.state = 'refused'
            rec.message_post(body=_('Đã từ chối bởi %s', self.env.user.name))

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(_('Phiếu đã hoàn tất, không thể hủy.'))
            rec.state = 'cancel'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ('refused', 'cancel'):
                raise UserError(_('Chỉ chuyển về Nháp khi phiếu đang Bị từ chối hoặc Đã hủy.'))
            rec.state = 'draft'

    def action_mark_in_transit(self):
        for rec in self:
            if rec.state != 'biz_approved':
                raise UserError(_('Phiếu chưa được duyệt nghiệp vụ.'))
            rec.state = 'goods_in_transit'
            rec._create_return_picking()
            rec._activity_schedule_for_role('otk',
                _('Tiếp nhận hàng trả về cho phiếu %s', rec.name))

    def action_qc_match(self):
        """OTK xác nhận hàng khớp khai báo → mở wizard phân loại."""
        self.ensure_one()
        if self.state not in ('goods_in_transit', 'qc_checking'):
            raise UserError(_('Chỉ xác nhận được khi đang ở bước OTK.'))
        self._check_role('otk')
        self.state = 'qc_checking'
        return {
            'type': 'ir.actions.act_window',
            'name': _('Phân loại hàng trả'),
            'res_model': 'vnop.return.qc.classify.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def action_qc_mismatch(self):
        self.ensure_one()
        if self.state not in ('goods_in_transit', 'qc_checking'):
            raise UserError(_('Chỉ thực hiện khi đang ở bước OTK.'))
        self._check_role('otk')
        if not (self.mismatch_note or '').strip():
            raise UserError(_('Hãy ghi rõ lệch khai báo ở mục "Ghi chú lệch khai báo" trước khi trả Sale.'))
        self.state = 'back_to_sales'
        self.message_post(body=_('OTK báo lệch khai báo: %s', self.mismatch_note))
        self._activity_schedule_for_role('accountant',
            _('Sale xác minh lại với đại lý cho phiếu %s', self.name))

    def action_resubmit(self):
        for rec in self:
            if rec.state != 'back_to_sales':
                raise UserError(_('Chỉ gửi lại được khi phiếu đang ở "Trả lại Sale xác minh".'))
            rec.state = 'submitted'
            rec.mismatch_note = False

    def action_finance_approve(self):
        for rec in self:
            if rec.state != 'qc_classified':
                raise UserError(_('Chỉ duyệt tài chính sau khi OTK đã phân loại.'))
            rec._check_role('chief_accountant')
            rec._create_refund()
            rec.state = 'done'
            rec.message_post(body=_('Kế toán trưởng đã duyệt và xuất hoá đơn giảm trừ.'))

    # ======================= SMART BUTTONS =======================
    def action_view_return_pickings(self):
        self.ensure_one()
        return self._smart_button_action(self.return_picking_ids,
                                          'stock.picking', _('Phiếu trả về kho'))

    def action_view_classify_pickings(self):
        self.ensure_one()
        return self._smart_button_action(self.classify_picking_ids,
                                          'stock.picking', _('Phiếu phân loại nội bộ'))

    def action_view_refund_moves(self):
        self.ensure_one()
        return self._smart_button_action(self.refund_move_ids,
                                          'account.move', _('Hoá đơn giảm trừ'))

    @staticmethod
    def _smart_button_action(records, res_model, name):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': res_model,
            'view_mode': 'list,form',
            'domain': [('id', 'in', records.ids)],
        }

    # ======================= STOCK / ACCOUNTING =======================
    def _get_return_source_location(self):
        """Vị trí nguồn = customer location (hàng từ đại lý về)."""
        return self.env.ref('stock.stock_location_customers')

    def _get_return_dest_location(self):
        """Vị trí đích trung gian = Kho Tạm (chưa QC)."""
        loc = self.env.ref('vnop_stock.location_temp_incoming', raise_if_not_found=False)
        if not loc:
            warehouse = self.env['stock.warehouse'].search(
                [('company_id', '=', self.company_id.id)], limit=1)
            loc = warehouse.lot_stock_id
        return loc

    def _find_source_delivery(self):
        """Tìm phiếu giao gốc (outgoing, done) phủ hết SP cần trả, để có thể
        dùng cơ chế trả hàng chuẩn của Odoo (giữ origin_returned_move_id +
        to_refund). Trả về rỗng nếu không có đơn gốc hoặc không phiếu nào phủ đủ
        → caller fallback tạo phiếu thủ công."""
        self.ensure_one()
        if not self.sale_order_id:
            return self.env['stock.picking']
        pickings = self.sale_order_id.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state == 'done')
        want = set(self.line_ids.mapped('product_id').ids)
        if not want:
            return self.env['stock.picking']
        for picking in pickings:
            done_products = set(picking.move_ids.filtered(
                lambda m: m.state == 'done').mapped('product_id').ids)
            if want <= done_products:
                return picking
        return self.env['stock.picking']

    def _create_return_via_wizard(self, source_picking, dst):
        """Dùng stock.return.picking._create_return() để tạo phiếu nhập trả có
        neo về move giao gốc (origin_returned_move_id) và set to_refund (giảm
        qty_delivered). Đích được redirect về Kho Tạm qua context (xem
        stock_return_picking.py). Trả về rỗng nếu không khớp được dòng nào."""
        self.ensure_one()
        wizard = self.env['stock.return.picking'].with_context(
            active_id=source_picking.id,
            active_model='stock.picking',
            vnop_return_dest_location_id=dst.id,
        ).create({'picking_id': source_picking.id})
        qty_by_product = {}
        for line in self.line_ids:
            qty_by_product.setdefault(line.product_id.id, 0.0)
            qty_by_product[line.product_id.id] += line.quantity
        matched = False
        for rl in wizard.product_return_moves:
            qty = qty_by_product.get(rl.product_id.id, 0.0)
            rl.quantity = qty
            if qty > 0:
                matched = True
            if 'to_refund' in rl._fields:
                rl.to_refund = bool(qty)
        if not matched:
            return self.env['stock.picking']
        return wizard._create_return()

    def _create_return_manual(self, dst):
        """Tạo phiếu nhập trả thủ công khi không xác định được phiếu giao gốc
        (vd: trả ngoại lệ không gắn đơn). Không có origin_returned_move_id."""
        self.ensure_one()
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company_id.id)], limit=1)
        picking_type = warehouse.in_type_id
        src = self._get_return_source_location()
        moves = [(0, 0, {
            'name': line.product_id.display_name,
            'product_id': line.product_id.id,
            'product_uom_qty': line.quantity,
            'product_uom': line.product_uom_id.id,
            'location_id': src.id,
            'location_dest_id': dst.id,
            'company_id': self.company_id.id,
        }) for line in self.line_ids]
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'picking_type_id': picking_type.id,
            'location_id': src.id,
            'location_dest_id': dst.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'move_ids': moves,
        })
        picking.action_confirm()
        return picking

    def _create_return_picking(self):
        self.ensure_one()
        if self.return_picking_ids:
            return self.return_picking_ids
        dst = self._get_return_dest_location()
        source_picking = self._find_source_delivery()
        picking = self.env['stock.picking']
        if source_picking:
            # Ưu tiên reuse cơ chế Odoo để giữ truy vết + qty_delivered.
            # Nếu wizard không tạo được (đã trả hết, không khớp dòng...) → fallback.
            try:
                picking = self._create_return_via_wizard(source_picking, dst)
            except UserError:
                picking = self.env['stock.picking']
        if not picking:
            picking = self._create_return_manual(dst)
        self.return_picking_ids = [(4, picking.id)]
        return picking

    def _create_refund(self):
        self.ensure_one()
        if not self.invoice_id:
            # Cho phép trường hợp không có hoá đơn gốc → tạo credit note thủ công
            move_vals = {
                'move_type': 'out_refund',
                'partner_id': self.partner_id.id,
                'invoice_user_id': self.salesperson_id.id,
                'invoice_origin': self.name,
                'ref': _('Trả hàng lỗi - %s', self.name),
                'invoice_line_ids': [(0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'name': line.product_id.display_name,
                }) for line in self.line_ids],
            }
            move = self.env['account.move'].create(move_vals)
        else:
            # Dùng wizard chuẩn account.move.reversal
            reversal_wiz = self.env['account.move.reversal'].with_context(
                active_model='account.move',
                active_ids=self.invoice_id.ids,
            ).create({
                'reason': _('Trả hàng lỗi - %s', self.name),
                'journal_id': self.invoice_id.journal_id.id,
            })
            action = reversal_wiz.refund_moves()
            move_id = action.get('res_id') or (action.get('domain') and action['domain'][0][2])
            if isinstance(move_id, list):
                move = self.env['account.move'].browse(move_id)
            else:
                move = self.env['account.move'].browse(move_id)
            # Cập nhật salesperson + ref
            move.write({
                'invoice_user_id': self.salesperson_id.id,
                'ref': _('Trả hàng lỗi - %s', self.name),
            })
        self.refund_move_ids = [(4, m, 0) for m in move.ids]
        return move
