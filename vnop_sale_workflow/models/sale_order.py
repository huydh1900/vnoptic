# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # -------------------------------------------------------------------------
    # State extension
    # -------------------------------------------------------------------------
    state = fields.Selection(
        selection_add=[
            ('to_approve_l1', 'Chờ duyệt L1'),
            ('to_approve_l2', 'Chờ duyệt L2'),
        ],
        ondelete={
            'to_approve_l1': 'set default',
            'to_approve_l2': 'set default',
        },
    )

    # -------------------------------------------------------------------------
    # Approval fields
    # -------------------------------------------------------------------------
    approval_level_required = fields.Selection(
        selection=[
            ('0', 'Không cần duyệt'),
            ('1', 'Quản lý'),
            ('2', 'Giám đốc'),
        ],
        string='Mức duyệt yêu cầu',
        compute='_compute_approval_level_required',
        store=True,
        tracking=True,
    )
    approver_l1_id = fields.Many2one(
        comodel_name='res.users',
        string='Người duyệt L1',
        readonly=True,
        tracking=True,
        copy=False,
    )
    approver_l2_id = fields.Many2one(
        comodel_name='res.users',
        string='Người duyệt L2',
        readonly=True,
        tracking=True,
        copy=False,
    )
    is_approval_locked = fields.Boolean(
        string='Đang chờ duyệt',
        compute='_compute_approval_locked',
    )

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------
    @api.depends('amount_total', 'order_line.discount', 'company_id')
    def _compute_approval_level_required(self):
        for order in self:
            company = order.company_id
            max_discount = max(
                (line.discount for line in order.order_line if line.discount),
                default=0.0,
            )
            amount = order.amount_total or 0.0

            if (
                amount >= company.workflow_approval_l2_threshold
                or max_discount >= company.discount_approval_l2_threshold
            ):
                order.approval_level_required = '2'
            elif (
                amount >= company.workflow_approval_l1_threshold
                or max_discount >= company.discount_approval_l1_threshold
            ):
                order.approval_level_required = '1'
            else:
                order.approval_level_required = '0'

    def _compute_approval_locked(self):
        for order in self:
            order.is_approval_locked = order.state in ('to_approve_l1', 'to_approve_l2')

    # -------------------------------------------------------------------------
    # Override action_confirm — gọi đúng super(), không bypass
    # -------------------------------------------------------------------------
    def action_confirm(self):
        # Cho phép xác nhận sau khi đã qua luồng duyệt (context flag set bởi action_approve_*)
        if not self.env.context.get('workflow_approval_passed'):
            for order in self:
                if order.approval_level_required != '0':
                    raise ValidationError(
                        _('Đơn hàng "%s" cần được duyệt trước khi xác nhận. '
                          'Vui lòng sử dụng nút "Yêu cầu duyệt".') % order.name
                    )
        return super().action_confirm()

    # -------------------------------------------------------------------------
    # Approval workflow actions
    # -------------------------------------------------------------------------
    def action_request_approval(self):
        """Gửi yêu cầu duyệt. Nếu không cần duyệt thì xác nhận luôn."""
        for order in self:
            order.ensure_one()
            if order.state not in ('draft', 'sent'):
                raise UserError(_('Chỉ có thể yêu cầu duyệt khi đơn ở trạng thái Nháp hoặc Đã gửi.'))

            if order.approval_level_required == '0':
                order.with_context(workflow_approval_passed=True).action_confirm()
            else:
                order.write({'state': 'to_approve_l1'})
                order.message_post(
                    body=_('Đơn hàng đã được gửi yêu cầu duyệt cấp %s.') % order.approval_level_required,
                )

    def action_approve_l1(self):
        """Duyệt L1 — yêu cầu nhóm group_sale_manager."""
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Bạn không có quyền duyệt cấp 1. Cần nhóm Quản lý bán hàng.'))

        for order in self:
            if order.state != 'to_approve_l1':
                raise UserError(_('Đơn "%s" không ở trạng thái chờ duyệt L1.') % order.name)

            order.write({'approver_l1_id': self.env.uid})

            if order.approval_level_required == '2':
                order.write({'state': 'to_approve_l2'})
                order.message_post(body=_('Đã duyệt L1. Đơn hàng chờ duyệt cấp Giám đốc.'))
            else:
                # level = 1 — xác nhận ngay sau khi duyệt L1
                order.write({'state': 'sent'})
                order.with_context(workflow_approval_passed=True).action_confirm()

    def action_approve_l2(self):
        """Duyệt L2 — yêu cầu nhóm group_sale_director."""
        if not self.env.user.has_group('vnop_sale_workflow.group_sale_director'):
            raise UserError(_('Bạn không có quyền duyệt cấp 2. Cần nhóm Giám đốc bán hàng.'))

        for order in self:
            if order.state != 'to_approve_l2':
                raise UserError(_('Đơn "%s" không ở trạng thái chờ duyệt L2.') % order.name)

            order.write({'approver_l2_id': self.env.uid})
            order.write({'state': 'sent'})
            order.with_context(workflow_approval_passed=True).action_confirm()

    def action_reject_approval(self):
        """Từ chối duyệt — trả về trạng thái 'sent', xóa approver fields."""
        for order in self:
            if order.state not in ('to_approve_l1', 'to_approve_l2'):
                raise UserError(_('Chỉ có thể từ chối khi đơn đang chờ duyệt.'))

            order.write({
                'state': 'sent',
                'approver_l1_id': False,
                'approver_l2_id': False,
            })
            order.message_post(body=_('Yêu cầu duyệt đã bị từ chối. Đơn hàng trả về trạng thái Đã gửi.'))
