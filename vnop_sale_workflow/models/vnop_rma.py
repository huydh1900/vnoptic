# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class VnopRma(models.Model):
    _name = 'vnop.rma'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Yêu cầu trả hàng (RMA)'
    _order = 'name desc'

    name = fields.Char(
        string='Mã RMA',
        default='New',
        readonly=True,
        copy=False,
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Đơn hàng gốc',
        required=True,
        ondelete='restrict',
        domain=[('state', 'in', ['sale', 'done'])],
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Khách hàng',
        related='sale_order_id.partner_id',
        store=True,
        readonly=True,
    )
    rma_line_ids = fields.One2many(
        comodel_name='vnop.rma.line',
        inverse_name='rma_id',
        string='Dòng sản phẩm trả',
    )
    reason_code = fields.Selection(
        selection=[
            ('defect', 'Hàng lỗi'),
            ('wrong_item', 'Sai mặt hàng'),
            ('customer_change', 'Khách đổi ý'),
            ('quality_issue', 'Lỗi chất lượng'),
            ('other', 'Khác'),
        ],
        string='Lý do trả hàng',
        required=True,
        tracking=True,
    )
    reason_note = fields.Text(string='Ghi chú thêm')
    state = fields.Selection(
        selection=[
            ('draft', 'Nháp'),
            ('submitted', 'Đã gửi'),
            ('approved', 'Đã duyệt'),
            ('rejected', 'Từ chối'),
            ('received', 'Đã nhận hàng'),
            ('refunded', 'Đã hoàn tiền'),
            ('replaced', 'Đã đổi hàng'),
            ('cancelled', 'Hủy'),
            ('done', 'Hoàn tất'),
        ],
        string='Trạng thái',
        default='draft',
        tracking=True,
    )
    resolution_type = fields.Selection(
        selection=[
            ('refund', 'Hoàn tiền'),
            ('replace', 'Đổi hàng'),
            ('credit_note', 'Giảm trừ công nợ'),
        ],
        string='Hình thức xử lý',
        required=True,
        default='refund',
        tracking=True,
    )
    picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string='Phiếu nhận hàng',
        readonly=True,
    )
    refund_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Phiếu hoàn tiền',
        readonly=True,
    )
    replacement_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Đơn đổi hàng',
        readonly=True,
    )
    approver_id = fields.Many2one(
        comodel_name='res.users',
        string='Người duyệt',
        readonly=True,
        tracking=True,
        copy=False,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Công ty',
        required=True,
        default=lambda self: self.env.company,
    )
    delivery_date = fields.Date(
        string='Ngày giao hàng',
        compute='_compute_delivery_date',
        store=True,
        help='Ngày giao hàng cuối cùng từ picking của đơn hàng gốc.',
    )

    # -------------------------------------------------------------------------
    # Compute
    # -------------------------------------------------------------------------
    @api.depends('sale_order_id.picking_ids.date_done', 'sale_order_id.picking_ids.state')
    def _compute_delivery_date(self):
        for rma in self:
            pickings = rma.sale_order_id.picking_ids.filtered(
                lambda p: p.state == 'done'
            )
            if pickings:
                rma.delivery_date = max(
                    p.date_done.date() if p.date_done else date.min
                    for p in pickings
                )
            else:
                rma.delivery_date = False

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    def action_submit(self):
        """Gửi yêu cầu RMA: kiểm tra cửa sổ thời gian, tạo sequence và incoming picking."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Chỉ có thể gửi RMA ở trạng thái Nháp.'))
        if not self.rma_line_ids:
            raise ValidationError(_('Vui lòng thêm ít nhất một sản phẩm cần trả.'))

        # Kiểm tra cửa sổ thời gian trả hàng
        rma_window_days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'vnop_sale_workflow.rma_window_days', default='30'
            )
        )
        if self.delivery_date:
            delta = (fields.Date.today() - self.delivery_date).days
            if delta > rma_window_days:
                raise ValidationError(
                    _('Đã vượt quá thời hạn trả hàng %d ngày. '
                      'Đơn hàng được giao ngày %s, hôm nay là ngày %s.')
                    % (rma_window_days, self.delivery_date, fields.Date.today())
                )

        # Sinh mã RMA
        sequence = self.env['ir.sequence'].next_by_code('vnop.rma')
        self.write({'name': sequence, 'state': 'submitted'})

        # Tạo incoming picking (nhận hàng trả về)
        self._create_return_picking()

        self.message_post(body=_('Yêu cầu trả hàng đã được gửi.'))

    def _create_return_picking(self):
        """Tạo stock.picking nhận hàng trả từ khách về kho."""
        origin_pickings = self.sale_order_id.picking_ids.filtered(
            lambda p: p.state == 'done' and p.picking_type_code == 'outgoing'
        )
        if not origin_pickings:
            self.message_post(body=_('Không tìm thấy phiếu giao hàng đã hoàn thành. Bỏ qua tạo phiếu nhận hàng.'))
            return

        # Lấy picking type nhận hàng của công ty
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id.company_id', '=', self.company_id.id),
        ], limit=1)
        if not picking_type:
            self.message_post(body=_('Không tìm thấy loại phiếu nhận hàng. Bỏ qua tạo phiếu nhận.'))
            return

        # Build move lines từ rma_line_ids
        move_vals_list = []
        for line in self.rma_line_ids:
            move_vals_list.append({
                'name': line.product_id.display_name or _('Hàng trả'),
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_returned,
                'product_uom': line.sale_line_id.product_uom.id,
                'location_id': picking_type.default_location_src_id.id or self.partner_id.property_stock_supplier.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
            })

        if not move_vals_list:
            return

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': self.partner_id.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'move_ids': [(0, 0, mv) for mv in move_vals_list],
        })
        self.picking_id = picking

    def action_approve(self):
        """Duyệt RMA — yêu cầu nhóm group_rma_approver."""
        if not self.env.user.has_group('vnop_sale_workflow.group_rma_approver'):
            raise UserError(_('Bạn không có quyền duyệt yêu cầu trả hàng.'))
        for rma in self:
            if rma.state != 'submitted':
                raise UserError(_('Chỉ có thể duyệt RMA ở trạng thái Đã gửi.'))
            rma.write({'state': 'approved', 'approver_id': self.env.uid})
            rma.message_post(body=_('Yêu cầu trả hàng đã được duyệt.'))

    def action_reject(self):
        """Từ chối RMA — yêu cầu nhóm group_rma_approver."""
        if not self.env.user.has_group('vnop_sale_workflow.group_rma_approver'):
            raise UserError(_('Bạn không có quyền từ chối yêu cầu trả hàng.'))
        for rma in self:
            if rma.state != 'submitted':
                raise UserError(_('Chỉ có thể từ chối RMA ở trạng thái Đã gửi.'))
            rma.write({'state': 'rejected'})
            rma.message_post(body=_('Yêu cầu trả hàng đã bị từ chối.'))

    def action_receive(self):
        """Xác nhận đã nhận hàng trả về."""
        for rma in self:
            if rma.state != 'approved':
                raise UserError(_('Chỉ có thể xác nhận nhận hàng khi RMA đã được duyệt.'))
            # Validate qty_received <= qty_returned trên từng line
            for line in rma.rma_line_ids:
                if line.qty_received > line.qty_returned:
                    raise ValidationError(
                        _('Sản phẩm "%s": số lượng nhận (%s) không được vượt số lượng trả (%s).')
                        % (line.product_id.display_name, line.qty_received, line.qty_returned)
                    )
            rma.write({'state': 'received'})
            rma.message_post(body=_('Đã nhận hàng trả về. Sẵn sàng xử lý.'))

    def action_refund(self):
        """Tạo phiếu hoàn tiền (account.move out_refund) từ các dòng RMA."""
        self.ensure_one()
        if self.state != 'received':
            raise UserError(_('Chỉ có thể hoàn tiền khi đã nhận hàng.'))

        # Tìm invoice gốc của đơn hàng (nếu có)
        origin_invoice = self.sale_order_id.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
        )[:1]

        invoice_line_vals = []
        for line in self.rma_line_ids:
            invoice_line_vals.append((0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.qty_received or line.qty_returned,
                'price_unit': line.unit_price,
                'name': line.product_id.display_name or _('Hàng trả'),
            }))

        move_vals = {
            'move_type': 'out_refund',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'invoice_origin': self.name,
            'invoice_line_ids': invoice_line_vals,
        }
        if origin_invoice:
            move_vals['reversed_entry_id'] = origin_invoice.id
        else:
            # Không có invoice gốc — ghi chú rõ
            move_vals['narration'] = _(
                'Hoàn tiền RMA %s. Không tìm thấy hóa đơn gốc đã xác nhận cho đơn hàng %s.'
            ) % (self.name, self.sale_order_id.name)

        refund_move = self.env['account.move'].create(move_vals)
        self.write({
            'refund_move_id': refund_move.id,
            'state': 'refunded',
        })
        self.message_post(
            body=_('Đã tạo phiếu hoàn tiền: <a href="#">%s</a>') % refund_move.name
        )
        # Chuyển sang done sau khi hoàn tiền
        self.write({'state': 'done'})

    def action_replace(self):
        """Tạo đơn hàng đổi hàng (sale.order) từ các dòng RMA."""
        self.ensure_one()
        if self.state != 'received':
            raise UserError(_('Chỉ có thể tạo đơn đổi hàng khi đã nhận hàng.'))

        new_order = self.sale_order_id.copy({
            'origin': self.name,
            'note': _('Đơn đổi hàng từ RMA %s') % self.name,
        })
        # Xóa tất cả order line, chỉ giữ lines từ RMA
        new_order.order_line.unlink()

        for line in self.rma_line_ids:
            self.env['sale.order.line'].create({
                'order_id': new_order.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_returned,
                'price_unit': line.unit_price,
                'product_uom': line.sale_line_id.product_uom.id,
            })

        self.write({
            'replacement_order_id': new_order.id,
            'state': 'replaced',
        })
        self.message_post(
            body=_('Đã tạo đơn đổi hàng: <a href="#">%s</a>') % new_order.name
        )
        self.write({'state': 'done'})

    def action_cancel(self):
        """Hủy RMA — không cho hủy khi đã done/refunded/replaced."""
        for rma in self:
            if rma.state in ('done', 'refunded', 'replaced'):
                raise UserError(
                    _('Không thể hủy RMA "%s" ở trạng thái "%s".') % (rma.name, rma.state)
                )
            rma.write({'state': 'cancelled'})
            rma.message_post(body=_('Yêu cầu trả hàng đã bị hủy.'))
