# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Contract(models.Model):
    _name = "contract"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _description = "Hợp đồng mua hàng"
    _order = "id desc"

    number = fields.Char(string="Số HĐ", copy=False, index=True)
    name = fields.Char(string="Tên hợp đồng", tracking=True, required=True)
    sign_date = fields.Date(string="Ngày ký HĐ", tracking=True)

    partner_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp",
        required=True,
        domain="[('supplier_rank','>',0)]",
        tracking=True,
    )
    partner_ref = fields.Char(string="Mã NCC", related="partner_id.ref", store=True, readonly=True)

    state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("waiting", "Chờ duyệt"),
            ("revision_requested", "Yêu cầu chỉnh sửa"),
            ("approved", "Đã duyệt"),
            ("cancel", "Hủy"),
        ],
        string="Trạng thái",
        default="draft",
        tracking=True,
        copy=False,
        index=True,
    )

    approved_date = fields.Datetime(string="Ngày duyệt", readonly=True, copy=False, tracking=True)
    approved_by = fields.Many2one("res.users", string="Người duyệt", readonly=True, copy=False, tracking=True)

    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        related="partner_id.property_purchase_currency_id",
        required=True,
    )
    # amount_total = fields.Monetary(
    #     string="Tổng giá trị HĐ",
    #     currency_field="currency_id",
    #     compute="_compute_totals",
    #     store=True,
    #     tracking=True,
    # )
    # total_qty = fields.Float(
    #     string="Tổng số lượng",
    #     compute="_compute_totals",
    #     store=True,
    # )

    # ====== Delivery / shipping ======
    incoterm_id = fields.Many2one("account.incoterms", string="Điều kiện giao hàng")
    shipment_date = fields.Date(string="Ngày dự kiến giao hàng", required=True)
    port_of_loading = fields.Char(string="Cảng xếp hàng")
    destination = fields.Char(string="Cảng/điểm đến")
    partial_shipment = fields.Boolean(string="Cho phép giao nhiều đợt", default=True)

    origin_country_id = fields.Many2one("res.country", string="Xuất xứ")

    packing = fields.Text(string="Quy cách đóng gói")
    quality_requirements = fields.Text(string="Yêu cầu chất lượng")

    # ====== Payment ======
    payment_term_id = fields.Many2one("account.payment.term", string="Điều khoản thanh toán")

    # ====== Bank info (dùng model chuẩn) ======
    beneficiary_bank_id = fields.Many2one(
        "res.partner.bank",
        string="Tài khoản thụ hưởng",
        domain="[('partner_id', 'in', [partner_id])]",
        help="Chọn tài khoản ngân hàng của nhà cung cấp (res.partner.bank).",
    )

    # ====== Docs / terms ======
    terms = fields.Html(string="Terms & Conditions")
    note = fields.Html(string="Ghi chú")

    attachment_ids = fields.Many2many(
        "ir.attachment",
        "contract_ir_attachment_rel",
        "contract_id",
        "attachment_id",
        string="Chứng từ/Hợp đồng",
    )

    # ====== PO links ======
    purchase_order_ids = fields.Many2many(
        "purchase.order",
        string="Đơn mua hàng",
        domain="[('partner_id','=', partner_id), ('state','in',('purchase','done'))]",
    )
    purchase_order_count = fields.Integer(string="Số PO", compute="_compute_purchase_order_count")

    # ====== Lines ======
    line_ids = fields.One2many("contract.line", "contract_id", string="Tổng hợp sản phẩm", copy=False)

    type_contract = fields.Selection(
        [
            ("domestic", "Trong nước"),
            ("foreign", "Nước ngoài"),
        ],
        string="Loại hợp đồng",
        default="foreign",
        copy=False,
        index=True,
        tracking=True,
    )

    product_count = fields.Integer(string="Số sản phẩm", compute="_compute_product_count")

    # @api.depends("line_ids", "line_ids.product_qty", "line_ids.price_subtotal")
    # def _compute_totals(self):
    #     for rec in self:
    #         rec.total_qty = sum(rec.line_ids.mapped("product_qty"))
    #         rec.amount_total = sum(rec.line_ids.mapped("price_subtotal"))

    def _compute_purchase_order_count(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)

    @api.depends("line_ids")
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.line_ids)

    def action_view_product(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Danh sách sản phẩm",
            "res_model": "contract.line",
            "view_mode": "list",
            "domain": [("contract_id", "=", self.id)],
            "context": {
                "default_contract_id": self.id,
                "create": False
            },
            "target": "current",
        }

    def action_approve(self):
        Schedule = self.env['delivery.schedule']
        for rec in self:
            if rec.state == "approved":
                continue

            rec.write({
                "state": "approved",
                "approved_date": fields.Datetime.now(),
                "approved_by": self.env.user.id,
            })

            existing_schedule = Schedule.search([
                ('contract_id', '=', rec.id)
            ], limit=1)

            if not existing_schedule:
                Schedule.create({
                    'partner_id': rec.partner_id.id,
                    'partner_ref': rec.partner_ref,
                    'contract_id': rec.id,
                    'delivery_datetime': rec.shipment_date,
                })

    def action_view_delivery_schedule(self):
        self.ensure_one()
        schedule = self.env["delivery.schedule"].search(
            [("contract_id", "=", self.id)],
            limit=1
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Lịch giao hàng",
            "res_model": "delivery.schedule",
            "view_mode": "form",
            "res_id": schedule.id,
            "target": "current",
        }

    def action_cancel(self):
        for rec in self:
            rec.write({"state": "cancel"})

    def action_request_revision(self):
        for rec in self:
            if rec.state != 'approved':
                continue
            rec.write({'state': 'revision_requested'})

    def action_allow_revision(self):
        for rec in self:
            if rec.state != 'revision_requested':
                continue
            rec.write({'state': 'draft'})


    def action_submit(self):
        for rec in self:
            if not rec.partner_id:
                raise ValidationError(_("Vui lòng chọn Nhà cung cấp trước khi gửi duyệt."))
            rec.write({'state': 'waiting'})

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        self.partner_ref = self.partner_id.ref
        self.purchase_order_ids = [(5, 0, 0)]
        self.line_ids = [(5, 0, 0)]

    @api.onchange("purchase_order_ids")
    def _onchange_purchase_order_ids_build_product_lines(self):
        """Tự động nạp dòng sản phẩm từ PO đã chọn vào hợp đồng."""
        for contract in self:
            line_commands = [(5, 0, 0)]

            for po in contract.purchase_order_ids:
                for line in po.order_line:
                    if not line.product_id or line.display_type:
                        continue

                    line_commands.append((0, 0, {
                        "product_id": line.product_id.id,
                        "uom_id": line.product_uom.id,
                        "currency_id": po.currency_id.id,
                        "product_qty": line.product_qty,
                        "qty_contract": line.product_qty,
                        "price_unit": line.price_unit,
                        "amount_total": line.price_subtotal,
                        "purchase_id": po.id,
                    }))

            contract.line_ids = line_commands
