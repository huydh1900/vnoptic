from odoo import models, fields, api
from odoo.exceptions import UserError
import datetime, time
from odoo.exceptions import ValidationError


class DeliverySchedule(models.Model):
    _name = 'delivery.schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'delivery_datetime desc'
    _rec_name = 'contract_id'
    _description = 'Lịch giao hàng'

    name = fields.Char(string='Đợt giao')
    delivery_datetime = fields.Datetime(
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
    contract_id = fields.Many2one('contract', string='Hợp đồng', required=True)

    description = fields.Text(
        string='Mô tả'
    )

    partner_id = fields.Many2one('res.partner', string='Nhà cung cấp', required=True)
    partner_ref = fields.Char(string='Mã NCC', related='partner_id.ref')

    purchase_ids = fields.Many2many(
        'purchase.order', related='contract_id.purchase_order_ids',
        string='Đơn mua hàng'
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
        ('draft', 'Dự kiến giao'),
        ('confirmed', 'Xác nhận hàng về'),
        ('partial', 'Đã giao một phần'),
        ('done', 'Đã giao đủ'),
        ('cancel', 'Huỷ'),
    ], default='draft', string='Trạng thái', tracking=True)

    picking_count = fields.Integer(compute='_compute_picking_count')

    color = fields.Integer(string="Color", compute="_compute_color", store=True)

    @api.depends('state')
    def _compute_color(self):
        mapping = {
            'draft': 1,  # xanh dương nhạt
            'confirmed': 2,  # xanh lá
            'partial': 3,  # vàng/cam
            'done': 10,  # xanh lá đậm
            'cancel': 4,  # đỏ
        }
        for rec in self:
            rec.color = mapping.get(rec.state, 0)

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    def action_confirmed(self):
        self.state = 'confirmed'

    def action_create_receipt(self):
        self.ensure_one()

        # Lấy đúng loại hoạt động bạn vừa tạo
        picking_type = self.env['stock.picking.type'].search([
            ('name', '=', 'Phiếu nhập kho tạm'),
            ('code', '=', 'incoming')
        ], limit=1)

        if not picking_type:
            raise UserError("Chưa cấu hình 'Phiếu nhập kho tạm'")

        picking = self.env['stock.picking'].create({
            'partner_id': self.contract_id.partner_id.id,
            'picking_type_id': picking_type.id,
            'origin': self.bill_number,
            'scheduled_date': self.delivery_datetime,
            'company_id': self.company_id.id,

            # lấy dúng location từ loại hoạt động
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,

            'delivery_schedule_id': self.id,
        })

        for line in self.contract_id.line_ids:
            self.env['stock.move'].create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom': line.product_uom.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            })

        picking.action_confirm()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
        }

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        for rec in self:
            if rec.contract_id:
                existing = self.search([
                    ('id', '!=', rec.id),
                    ('contract_id', '=', rec.contract_id.id)
                ], limit=1)

                if existing:
                    raise ValidationError(
                        "Hợp đồng này đã được gán cho lịch giao hàng với số vận đơn: %s."
                        % (existing.bill_number or "N/A")
                    )

    def action_view_contract(self):
        self.ensure_one()
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

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for rec in self:
            rec.contract_id = rec.purchase_ids = [(5, 0, 0)]
