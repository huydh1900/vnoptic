# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Contract(models.Model):
    _name = "contract"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'number'
    _description = "Hợp đồng mua hàng"
    _order = "id desc"

    number = fields.Char(string="Số HĐ", copy=False, index=True, required=True)
    partner_id = fields.Many2one("res.partner", string="Nhà cung cấp", required=True,
                                 domain="[('supplier_rank','>',0)]")
    partner_ref = fields.Char(string='Mã NCC')
    state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("waiting", "Chờ duyệt"),
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
        string="Đơn vị tiền tệ",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )

    terms = fields.Html(string="Terms & Conditions")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "contract_ir_attachment_rel",
        "contract_id",
        "attachment_id",
        string="Chứng từ/Hợp đồng",
    )

    purchase_order_ids = fields.Many2many("purchase.order", string="Đơn mua hàng",
                                          domain="[('partner_id','=', partner_id), ('state','in',('purchase','done'))]", )

    line_ids = fields.One2many(
        "contract.line",
        "contract_id",
        string="Tổng hợp sản phẩm",
        copy=False,
    )

    purchase_order_count = fields.Integer(
        string="Số PO",
        compute="_compute_purchase_order_count",
        store=False,
    )

    type_contract = fields.Selection(
        [
            ("domestic", "Trong nước"),
            ("foreign", "Nước ngoài"),
        ],
        string="Loại hợp đồng",
        default="foreign",
        copy=False,
        index=True,
    )

    note = fields.Text()
    product_count = fields.Integer(string='Số sản phẩm', compute="_compute_product_count")

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
        for rec in self:
            if rec.state != "draft":
                continue
            rec.write({
                "state": "approved",
                "approved_date": fields.Datetime.now(),
                "approved_by": self.env.user.id,
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

    @api.depends("purchase_order_ids")
    def _compute_purchase_order_count(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)

    def action_view_purchase_orders(self):
        self.ensure_one()
        action = self.env.ref("purchase.purchase_form_action").read()[0]
        action["domain"] = [("id", "in", self.purchase_order_ids.ids)]
        action["context"] = {
            "default_partner_id": self.partner_id.id,
            "create": False,
            "edit": False,
            "delete": False,
        }
        return action

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        self.partner_ref = self.partner_id.ref
        self.purchase_order_ids = [(5, 0, 0)]
        self.line_ids = [(5, 0, 0)]

    @api.onchange("purchase_order_ids")
    def _onchange_purchase_order_ids_build_product_lines(self):
        """
        Chọn PO A -> đổ line của PO A (1-1 theo từng order_line)
        Thêm PO B -> append thêm line, KHÔNG cộng dồn
        Bỏ PO -> rebuild lại theo danh sách PO hiện tại
        """
        for contract in self:
            commands = [(5, 0, 0)]  # clear

            for po in contract.purchase_order_ids:
                for line in po.order_line:
                    if not line.product_id or line.display_type:
                        continue

                    qty = line.product_qty
                    price_unit = line.price_unit
                    subtotal = line.price_subtotal

                    commands.append((0, 0, {
                        "product_id": line.product_id.id,
                        "product_uom": line.product_uom.id,
                        "product_qty": qty,
                        "price_unit": price_unit,
                        "amount_total": subtotal,
                        'purchase_id': po.id,

                    }))

            contract.line_ids = commands
