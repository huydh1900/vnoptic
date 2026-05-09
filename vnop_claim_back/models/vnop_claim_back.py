# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class VnopClaimBack(models.Model):
    _name = 'vnop.claim.back'
    _description = 'Báo cáo saleout & claim back đại lý'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_from desc, name desc'

    name = fields.Char(
        string='Số hiệu',
        default='New',
        readonly=True,
        copy=False,
    )
    dealer_id = fields.Many2one(
        comodel_name='res.partner',
        string='Đại lý',
        required=True,
        tracking=True,
        domain=[('dealer_tier_id', '!=', False)],
    )
    period_from = fields.Date(string='Từ ngày', required=True, tracking=True)
    period_to = fields.Date(string='Đến ngày', required=True, tracking=True)
    line_ids = fields.One2many(
        comodel_name='vnop.claim.back.line',
        inverse_name='claim_id',
        string='Dòng saleout',
        copy=True,
    )
    total_saleout_amount = fields.Monetary(
        string='Tổng doanh số',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_claim_amount = fields.Monetary(
        string='Tổng claim back',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    claim_pct_used = fields.Float(
        string='% Claim back áp dụng',
        compute='_compute_claim_pct',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Nháp'),
            ('uploaded', 'Đã upload'),
            ('confirmed', 'Đã xác nhận'),
            ('posted', 'Đã ghi sổ'),
            ('done', 'Hoàn tất'),
            ('cancelled', 'Hủy'),
        ],
        default='draft',
        tracking=True,
        copy=False,
        string='Trạng thái',
    )
    excel_file = fields.Binary(string='File Excel', attachment=True)
    excel_filename = fields.Char(string='Tên file')
    refund_move_id = fields.Many2one(
        comodel_name='account.move',
        string='HĐ giảm trừ',
        readonly=True,
        ondelete='restrict',
        copy=False,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Công ty',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
    )

    # ---------- constraints ----------

    @api.constrains('period_from', 'period_to')
    def _check_period(self):
        for rec in self:
            if rec.period_from and rec.period_to and rec.period_from > rec.period_to:
                raise UserError(_('Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc.'))

    # ---------- computes ----------

    @api.depends('line_ids.amount_saleout', 'line_ids.claim_amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_saleout_amount = sum(rec.line_ids.mapped('amount_saleout'))
            rec.total_claim_amount = sum(rec.line_ids.mapped('claim_amount'))

    @api.depends('dealer_id', 'dealer_id.dealer_tier_id', 'dealer_id.dealer_tier_id.claim_pct')
    def _compute_claim_pct(self):
        default_pct = float(
            self.env['ir.config_parameter'].sudo().get_param(
                'vnop_claim_back.default_claim_pct', default='5.0'
            )
        )
        for rec in self:
            tier = rec.dealer_id.dealer_tier_id if rec.dealer_id else False
            if tier and tier.claim_pct:
                rec.claim_pct_used = tier.claim_pct
            else:
                rec.claim_pct_used = default_pct

    # ---------- ORM overrides ----------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('vnop.claim.back') or 'New'
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state in ('posted', 'done'):
                raise UserError(
                    _('Không thể xóa bản ghi "%s" ở trạng thái Đã ghi sổ hoặc Hoàn tất.') % rec.name
                )
        return super().unlink()

    # ---------- workflow actions ----------

    def action_confirm(self):
        """Chuyển trạng thái uploaded -> confirmed. Yêu cầu group_sale_manager."""
        self._check_access_rights_sale_manager()
        for rec in self:
            if rec.state != 'uploaded':
                raise UserError(_('Chỉ có thể xác nhận bản ghi ở trạng thái Đã upload.'))
            rec.state = 'confirmed'

    def action_post(self):
        """Chuyển confirmed -> posted. Tạo credit note cấn trừ công nợ. Yêu cầu group_account_manager."""
        self._check_access_rights_account_manager()
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_('Chỉ có thể ghi sổ bản ghi ở trạng thái Đã xác nhận.'))
            if rec.refund_move_id:
                raise UserError(_('Đã tạo HĐ giảm trừ cho bản ghi "%s".') % rec.name)
            rec._create_refund_move()
            rec.state = 'posted'

    def action_done(self):
        """Chuyển posted -> done."""
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Chỉ có thể hoàn tất bản ghi ở trạng thái Đã ghi sổ.'))
            rec.state = 'done'

    def action_cancel(self):
        """Hủy bản ghi từ draft/uploaded/confirmed."""
        self._check_access_rights_sale_manager()
        for rec in self:
            if rec.state not in ('draft', 'uploaded', 'confirmed'):
                raise UserError(
                    _('Chỉ có thể hủy bản ghi ở trạng thái Nháp, Đã upload hoặc Đã xác nhận.')
                )
            rec.state = 'cancelled'

    def action_set_draft(self):
        """Chuyển cancelled -> draft."""
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Chỉ có thể đặt về nháp từ trạng thái Hủy.'))
            rec.state = 'draft'

    def action_open_refund_move(self):
        """Smart button mở HĐ giảm trừ."""
        self.ensure_one()
        if not self.refund_move_id:
            raise UserError(_('Chưa có HĐ giảm trừ.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.refund_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ---------- private helpers ----------

    def _create_refund_move(self):
        """Tạo account.move out_refund và post ngay."""
        self.ensure_one()
        company = self.company_id
        dealer = self.dealer_id.with_company(company)

        # Validate AR account
        ar_account = dealer.property_account_receivable_id
        if not ar_account:
            raise UserError(
                _('Đại lý "%s" chưa cấu hình tài khoản công nợ phải thu.') % self.dealer_id.name
            )

        # Lấy sales journal của công ty
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', company.id)],
            limit=1,
        )
        if not journal:
            raise UserError(_('Không tìm thấy nhật ký bán hàng cho công ty "%s".') % company.name)

        move_vals = {
            'move_type': 'out_refund',
            'partner_id': self.dealer_id.id,
            'journal_id': journal.id,
            'company_id': company.id,
            'invoice_date': fields.Date.context_today(self),
            'ref': self.name,
            'invoice_line_ids': [(0, 0, {
                'name': 'Claim back ' + self.name,
                'account_id': ar_account.id,
                'quantity': 1,
                'price_unit': self.total_claim_amount,
                'tax_ids': [],
            })],
        }
        move = self.env['account.move'].create(move_vals)
        move._post(soft=False)
        self.refund_move_id = move.id

    def _check_access_rights_sale_manager(self):
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Bạn cần quyền Quản lý bán hàng để thực hiện thao tác này.'))

    def _check_access_rights_account_manager(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Bạn cần quyền Quản lý kế toán để thực hiện thao tác này.'))
