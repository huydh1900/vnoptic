# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class VnopOrderRequest(models.Model):
    _name = 'vnop.order.request'
    _description = 'B2B Order Request (Nhu cầu đặt hàng đại lý)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Số đơn', required=True, copy=False, readonly=True,
        default=lambda self: _('New'), tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Đại lý', required=True, tracking=True,
        index=True,
    )
    commercial_partner_id = fields.Many2one(
        'res.partner', related='partner_id.commercial_partner_id',
        store=True, index=True,
    )
    pricelist_id = fields.Many2one(
        'product.pricelist', string='Bảng giá',
        default=lambda self: self._default_pricelist_id(),
    )
    currency_id = fields.Many2one(
        'res.currency', string='Tiền tệ',
        compute='_compute_currency_id', store=True,
    )

    @api.model
    def _default_pricelist_id(self):
        vnd = self.env.ref('base.VND', raise_if_not_found=False)
        if not vnd:
            return False
        return self.env['product.pricelist'].search([
            ('currency_id', '=', vnd.id),
            ('company_id', 'in', (False, self.env.company.id)),
        ], limit=1).id or False
    date_request = fields.Date(
        string='Ngày yêu cầu', default=fields.Date.context_today, tracking=True,
    )
    note = fields.Text(string='Ghi chú')
    state = fields.Selection(
        [
            ('draft', 'Nháp'),
            ('submitted', 'Đã gửi'),
            ('quoted', 'Đã báo giá'),
            ('cancelled', 'Đã hủy'),
        ],
        default='draft', required=True, tracking=True, copy=False,
    )
    line_ids = fields.One2many(
        'vnop.order.request.line', 'request_id', string='Dòng đơn',
        copy=True,
    )
    sale_order_ids = fields.One2many(
        'sale.order', 'order_request_id', string='Báo giá',
    )
    sale_order_count = fields.Integer(compute='_compute_sale_order_count')
    amount_total = fields.Monetary(
        string='Tổng tiền', compute='_compute_amount_total', store=True,
        currency_field='currency_id',
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    user_id = fields.Many2one(
        'res.users', string='Nhân viên phụ trách', tracking=True,
    )

    @api.depends('pricelist_id', 'company_id')
    def _compute_currency_id(self):
        vnd = self.env.ref('base.VND', raise_if_not_found=False)
        for rec in self:
            rec.currency_id = (
                rec.pricelist_id.currency_id
                or vnd
                or rec.company_id.currency_id
            )

    @api.depends('line_ids.price_subtotal')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('price_subtotal'))

    @api.depends('sale_order_ids')
    def _compute_sale_order_count(self):
        for rec in self:
            rec.sale_order_count = len(rec.sale_order_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'vnop.order.request'
                ) or _('New')
        return super().create(vals_list)

    # ----- Helpers -----

    def _get_price_unit(self, product, qty=1.0):
        """Lấy đơn giá theo pricelist của request (fallback list_price)."""
        self.ensure_one()
        if self.pricelist_id and product:
            return self.pricelist_id._get_product_price(
                product, qty, uom=product.uom_id,
                date=self.date_request or fields.Date.today(),
            )
        return product.lst_price if product else 0.0

    # ----- Workflow actions -----

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Chỉ đơn nháp mới có thể gửi."))
            if not rec.line_ids:
                raise UserError(_("Đơn chưa có sản phẩm nào."))
            rec.state = 'submitted'

    def action_cancel(self):
        for rec in self:
            if rec.state in ('quoted',):
                raise UserError(_(
                    "Đơn đã có báo giá, không thể hủy. Hãy hủy báo giá trước."
                ))
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state == 'quoted':
                raise UserError(_(
                    "Đơn đã có báo giá, không thể đưa về nháp."
                ))
            rec.state = 'draft'

    def action_create_quotation(self):
        self.ensure_one()
        if self.state not in ('submitted', 'quoted'):
            raise UserError(_(
                "Chỉ tạo báo giá từ đơn đã gửi."
            ))
        if not self.line_ids:
            raise UserError(_("Đơn chưa có sản phẩm nào."))

        so_vals = {
            'partner_id': self.partner_id.id,
            'order_request_id': self.id,
            'origin': self.name,
            'order_line': [
                (0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.name or line.product_id.display_name,
                    'product_uom_qty': line.product_uom_qty,
                    'product_uom': line.product_uom.id,
                    'price_unit': line.price_unit,
                }) for line in self.line_ids
            ],
        }
        if self.pricelist_id:
            so_vals['pricelist_id'] = self.pricelist_id.id
        if self.user_id:
            so_vals['user_id'] = self.user_id.id

        so = self.env['sale.order'].create(so_vals)
        self.state = 'quoted'

        return {
            'type': 'ir.actions.act_window',
            'name': _("Báo giá"),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': so.id,
        }

    def action_view_quotations(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _("Báo giá"),
            'res_model': 'sale.order',
            'domain': [('order_request_id', '=', self.id)],
        }
        if self.sale_order_count == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.sale_order_ids.id,
            })
        else:
            action['view_mode'] = 'list,form'
        return action


class VnopOrderRequestLine(models.Model):
    _name = 'vnop.order.request.line'
    _description = 'B2B Order Request Line'
    _order = 'request_id, sequence, id'

    request_id = fields.Many2one(
        'vnop.order.request', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        'product.product', string='Sản phẩm', required=True,
        domain=[('sale_ok', '=', True)],
    )
    name = fields.Char(string='Mô tả')
    product_uom_qty = fields.Float(
        string='Số lượng', default=1.0, digits='Product Unit of Measure',
    )
    product_uom = fields.Many2one('uom.uom', string='Đơn vị')
    price_unit = fields.Monetary(
        string='Đơn giá', currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='request_id.currency_id', store=True,
    )
    price_subtotal = fields.Monetary(
        string='Thành tiền', compute='_compute_price_subtotal', store=True,
        currency_field='currency_id',
    )
    note = fields.Char(string='Ghi chú')

    @api.depends('product_uom_qty', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.product_uom_qty * line.price_unit

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return
        if not self.name:
            self.name = self.product_id.display_name
        if not self.product_uom:
            self.product_uom = self.product_id.uom_id
        if not self.price_unit and self.request_id:
            self.price_unit = self.request_id._get_price_unit(
                self.product_id, self.product_uom_qty or 1.0,
            )
