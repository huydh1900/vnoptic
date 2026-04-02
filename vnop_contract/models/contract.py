# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


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
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

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

    delivery_state = fields.Selection(
        [
            ("expected", "Dự kiến giao"),
            ("partial", "Đã giao 1 phần"),
            ("done", "Đã giao đủ"),
            ("cancel", "Hủy"),
        ],
        string="Trạng thái giao",
        default="expected",
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
        readonly=False,
    )
    amount_total = fields.Monetary(
        string="Tổng giá trị HĐ",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        tracking=True,
    )
    total_qty = fields.Float(
        string="Tổng SL hợp đồng",
        compute="_compute_totals",
        store=True,
    )
    total_received_qty = fields.Float(
        string="Tổng SL đã nhận",
        compute="_compute_totals",
        store=True,
    )
    total_missing_qty = fields.Float(
        string="Tổng SL còn thiếu",
        compute="_compute_totals",
        store=True,
    )
    quantity_uom_id = fields.Many2one("uom.uom", string="Đơn vị số lượng")

    # ====== Delivery / shipping ======
    incoterm_id = fields.Many2one("account.incoterms", string="Điều kiện giao hàng")
    shipment_date = fields.Date(string="Ngày giao hàng")
    port_of_loading = fields.Char(string="Cảng xuất hàng")
    destination = fields.Char(string="Cảng đích")
    partial_shipment = fields.Boolean(string="Cho phép giao nhiều đợt", default=True)

    origin_country_id = fields.Many2one("res.country", string="Xuất xứ")
    quality_requirements = fields.Text(string="Yêu cầu chất lượng")
    packing = fields.Text(string="Quy cách đóng gói")

    # ====== Payment ======
    payment_term_id = fields.Many2one("account.payment.term", string="Điều khoản thanh toán")
    remittance = fields.Text(
        string="Phương thức thanh toán",
        help="Mô tả đặt cọc/TT trước giao hàng/TT sau giao hàng hoặc điều kiện khác.",
    )

    # ====== Bank info (dùng model chuẩn) ======
    beneficiary_bank_id = fields.Many2one(
        "res.partner.bank",
        string="Tài khoản thụ hưởng",
        domain="[('partner_id', 'in', [partner_id])]",
        help="Chọn tài khoản ngân hàng của nhà cung cấp (res.partner.bank).",
    )
    beneficiary_name = fields.Char(
        related="beneficiary_bank_id.acc_holder_name",
        string="Người thụ hưởng",
        readonly=True,
        store=True,
    )
    advising_bank_name = fields.Char(
        related="beneficiary_bank_id.bank_name",
        string="Tên ngân hàng",
        readonly=True,
        store=True,
    )
    branch_code = fields.Char(
        related="beneficiary_bank_id.bank_id.street2",
        string="Chi nhánh",
        readonly=True,
        store=True,
    )
    bank_address = fields.Char(
        related="beneficiary_bank_id.bank_id.street",
        string="Địa chỉ Ngân hàng",
        readonly=True,
        store=True,
    )
    account_no = fields.Char(
        related="beneficiary_bank_id.acc_number",
        string="Số tài khoản",
        readonly=True,
        store=True,
    )
    swift_code = fields.Char(
        related="beneficiary_bank_id.bank_bic",
        string="Mã swift",
        readonly=True,
        store=True,
    )

    note = fields.Html(string="Ghi chú")

    attachment_ids = fields.Many2many(
        "ir.attachment",
        "contract_ir_attachment_rel",
        "contract_id",
        "attachment_id",
        string="Chứng từ/Hợp đồng",
    )

    receipt_ids = fields.One2many("stock.picking", "contract_id", string="Phiếu nhập kho", readonly=True)
    receipt_count_open = fields.Integer(compute="_compute_receipt_metrics", string="Số phiếu nhập kho")

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

    @api.depends("line_ids.product_qty", "line_ids.qty_received", "line_ids.amount_total")
    def _compute_totals(self):
        for rec in self:
            rec.total_qty = sum(rec.line_ids.mapped("product_qty"))
            rec.total_received_qty = sum(
                min(line.qty_received, line.product_qty) for line in rec.line_ids
            )
            rec.total_missing_qty = sum(
                max(line.product_qty - line.qty_received, 0.0) for line in rec.line_ids
            )
            rec.amount_total = sum(rec.line_ids.mapped("amount_total"))

    @api.depends("receipt_ids", "receipt_ids.state")
    def _compute_receipt_metrics(self):
        if not self.ids:
            for rec in self:
                rec.receipt_count_open = 0
            return
        StockPicking = self.env["stock.picking"]
        all_pickings = StockPicking.search([
            "|",
            ("contract_id", "in", self.ids),
            ("move_ids_without_package.contract_id", "in", self.ids),
            ("picking_type_code", "=", "incoming"),
            ("state", "=", "done"),
        ])
        count_by_contract = {}
        for pick in all_pickings:
            cid = pick.contract_id.id
            if cid:
                count_by_contract[cid] = count_by_contract.get(cid, 0) + 1
        for rec in self:
            rec.receipt_count_open = count_by_contract.get(rec.id, 0)

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
            if rec.state == "approved":
                continue

            rec.write({
                "state": "approved",
                "approved_date": fields.Datetime.now(),
                "approved_by": self.env.user.id,
            })

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
            if not rec.shipment_date:
                raise ValidationError(_("Ngày giao hàng không được để trống!"))
            if not rec.line_ids:
                raise ValidationError(_("Hợp đồng phải có ít nhất một dòng sản phẩm."))
            rec._check_fifo_valuation()
            rec.write({'state': 'waiting'})

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        self.partner_ref = self.partner_id.ref
        self.line_ids = [(5, 0, 0)]
        self.beneficiary_bank_id = False

    def action_view_receipts(self):
        raise UserError(_("Vui lòng thao tác tại Lịch giao hàng."))

    def action_view_otk(self):
        raise UserError(_("Vui lòng thao tác tại Lịch giao hàng."))

    def _check_fifo_valuation(self):
        """Bắt buộc sản phẩm trong hợp đồng dùng FIFO + định giá tự động."""
        for contract in self:
            invalid_lines = contract.line_ids.filtered(
                lambda line: (
                        line.product_id.type == 'product'
                        and (
                                line.product_id.categ_id.property_cost_method != 'fifo'
                                or line.product_id.categ_id.property_valuation != 'real_time'
                        )
                )
            )
            if not invalid_lines:
                continue

            details = "\n".join(
                "- %s (Nhóm: %s, Costing: %s, Valuation: %s)" % (
                    line.product_id.display_name,
                    line.product_id.categ_id.display_name,
                    line.product_id.categ_id.property_cost_method,
                    line.product_id.categ_id.property_valuation,
                )
                for line in invalid_lines
            )

            raise ValidationError(_(
                "Các sản phẩm sau chưa dùng FIFO hoặc chưa bật Automated Valuation:\n%s\n"
                "Vui lòng chỉnh Product Category trước khi gửi duyệt hợp đồng."
            ) % details)

    @api.model
    def cleanup_legacy_contract_otk_records(self):
        legacy_xmlids = [
            "vnop_contract.seq_contract_otk",
            "vnop_contract.view_contract_otk_tree",
            "vnop_contract.view_contract_otk_form",
            "vnop_contract.action_contract_otk",
            "vnop_contract.access_contract_otk_user",
            "vnop_contract.access_contract_otk_line_user",
            "vnop_contract.access_contract_otk_line_lot_user",
        ]
        for xmlid in legacy_xmlids:
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                record.sudo().unlink()
