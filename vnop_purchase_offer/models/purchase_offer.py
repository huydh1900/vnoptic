# -*- coding: utf-8 -*-
import base64
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PurchaseOffer(models.Model):
    _name = "purchase.offer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Đề nghị mua hàng"
    _order = "id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Mã ĐNMH",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("Mới"),
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Nhà cung cấp",
        required=True,
        domain="[('supplier_rank', '>', 0)]",
        tracking=True,
    )
    partner_ref = fields.Char(string="Mã NCC", related="partner_id.ref", store=True, readonly=True)
    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
    )
    purchaser_id = fields.Many2one(
        "res.users",
        string="Người mua",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Tiền tệ",
        related="partner_id.property_purchase_currency_id",
        readonly=False,
        required=True,
    )
    exchange_rate = fields.Float(
        string="Tỷ giá",
        digits=(12, 2),
        help="Tỷ giá quy đổi sang VND (lấy từ res.currency.rate, có thể chỉnh tay)"
    )

    def _get_exchange_rate_for_currency(self, currency):
        self.ensure_one()
        if not currency:
            return 0.0
        if currency.name == "VND":
            return 1.0
        company = self.company_id or self.env.company
        rate = self.env["res.currency.rate"].search([
            ("currency_id", "=", currency.id),
            ("name", "<=", fields.Date.context_today(self)),
            ("company_id", "in", [company.id, False]),
        ], order="company_id desc, name desc", limit=1)
        # Odoo lưu rate = 1/vnd_per_unit → đảo lại để ra VND thực
        return round(1.0 / rate.rate, 2) if rate and rate.rate != 0 else 0.0

    @api.onchange("currency_id")
    def _onchange_currency_id_get_rate(self):
        for rec in self:
            rec.exchange_rate = rec._get_exchange_rate_for_currency(rec.currency_id)

    follow_up_date = fields.Date(string="Ngày hàng về dự kiến", tracking=True)
    approved_by = fields.Many2one("res.users", string="Người duyệt", readonly=True, copy=False, tracking=True)
    approved_date = fields.Datetime(string="Thời gian duyệt", readonly=True, copy=False, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Nháp"),
            ("waiting_approval", "Chờ duyệt"),
            ("approved", "Đã duyệt"),
            ("converted", "Đã chuyển hợp đồng"),
            ("cancelled", "Đã hủy"),
        ],
        string="Trạng thái",
        default="draft",
        tracking=True,
        copy=False,
    )
    note = fields.Text(string="Ghi chú nội bộ")
    line_ids = fields.One2many("purchase.offer.line", "offer_id", string="Danh sách sản phẩm", copy=True)
    contract_id = fields.Many2one("contract", string="Hợp đồng", readonly=True, copy=False)
    total_qty = fields.Float(
        string="Tổng SL dự kiến",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_qty_received = fields.Float(
        string="Tổng SL đã nhận",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    amount_total = fields.Monetary(
        string="Tổng giá trị dự kiến",
        compute="_compute_totals",
        store=True,
        currency_field="currency_id",
    )
    line_count = fields.Integer(string="Số dòng", compute="_compute_line_count")
    followup_alert_sent = fields.Boolean(string="Đã gửi cảnh báo theo dõi", copy=False, default=False)
    has_received = fields.Boolean(compute='_compute_has_received')

    @api.depends('line_ids.qty_received')
    def _compute_has_received(self):
        for rec in self:
            rec.has_received = any(l.qty_received > 0 for l in rec.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("Mới")) == _("Mới"):
                vals["name"] = sequence.next_by_code("purchase.offer") or _("Mới")
        return super().create(vals_list)

    @api.onchange("partner_id")
    def _onchange_partner_id_clear_lines(self):
        self.line_ids = [(5, 0, 0)]
        self.exchange_rate = self._get_exchange_rate_for_currency(self.currency_id)

    def write(self, vals):
        if "follow_up_date" in vals:
            vals["followup_alert_sent"] = False
        return super().write(vals)

    @api.depends("line_ids.quantity", "line_ids.subtotal", "line_ids.qty_received")
    def _compute_totals(self):
        for rec in self:
            rec.total_qty = sum(rec.line_ids.mapped("quantity"))
            rec.total_qty_received = sum(rec.line_ids.mapped("qty_received"))
            rec.amount_total = sum(rec.line_ids.mapped("subtotal"))

    @api.depends("line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.constrains("line_ids")
    def _check_lines_exist(self):
        for rec in self:
            if rec.state in ("waiting_approval", "approved", "converted") and not rec.line_ids:
                raise ValidationError(_("Đề nghị mua hàng phải có ít nhất một dòng sản phẩm."))

    def action_submit(self):
        if any(rec.state != "draft" for rec in self):
            raise UserError(_("Chỉ đề nghị mua hàng ở trạng thái Nháp mới được gửi duyệt."))
        self._validate_before_approval()
        self.write({"state": "waiting_approval"})

    def action_approve(self):
        if any(rec.state != "waiting_approval" for rec in self):
            raise UserError(_("Chỉ đề nghị mua hàng ở trạng thái Chờ duyệt mới được phê duyệt."))
        self._validate_before_approval()
        self.write({
            "state": "approved",
            "approved_by": self.env.user.id,
            "approved_date": fields.Datetime.now(),
        })

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def _validate_before_approval(self):
        for rec in self:
            if not rec.partner_id:
                raise ValidationError(_("Bạn cần chọn nhà cung cấp."))
            if not rec.line_ids:
                raise ValidationError(_("Bạn cần nhập ít nhất một sản phẩm."))

    def _validate_for_contract_creation(self):
        if not self:
            raise UserError(_("Bạn cần chọn ít nhất một đề nghị mua hàng đã duyệt."))

        invalid_state = self.filtered(lambda rec: rec.state != "approved")
        if invalid_state:
            names = ", ".join(invalid_state.mapped("display_name"))
            raise UserError(
                _("Chỉ các đề nghị ở trạng thái Đã duyệt mới được gom hợp đồng. Không hợp lệ: %s") % names
            )

        linked = self.filtered("contract_id")
        if linked:
            names = ", ".join(linked.mapped("display_name"))
            raise UserError(_("Các đề nghị sau đã được gắn hợp đồng: %s") % names)

        partners = self.mapped("partner_id")
        if len(partners) > 1:
            raise UserError(_("Chỉ được gom các Đề nghị mua hàng cùng một nhà cung cấp vào một hợp đồng."))

        companies = self.mapped("company_id")
        if len(companies) > 1:
            raise UserError(_("Chỉ được gom các Đề nghị mua hàng cùng một công ty vào một hợp đồng."))

        currencies = self.mapped("currency_id")
        if len(currencies) > 1:
            raise UserError(_("Chỉ được gom các Đề nghị mua hàng cùng một loại tiền tệ vào một hợp đồng."))

    def _prepare_contract_line_commands(self):
        self.ensure_one()
        return [
            (
                0,
                0,
                {
                    "product_id": line.product_id.id,
                    "uom_id": line.uom_id.id,
                    "currency_id": self.currency_id.id,
                    "product_qty": line.quantity,
                    "price_unit": line.expected_price,
                    "amount_total": line.subtotal,
                    "purchase_offer_line_id": line.id,
                },
            )
            for line in self.line_ids
        ]

    def _build_contract_note(self):
        notes = []
        for rec in self:
            if rec.note:
                notes.append(_("%s: %s") % (rec.display_name, rec.note))
        if not notes:
            return False
        return "<br/>".join(notes)

    def _get_contract_name(self):
        self.ensure_one()
        return self.name

    def _prepare_contract_vals(self):
        self._validate_for_contract_creation()
        first = self[0]
        first_uom = self.mapped("line_ids.uom_id")[:1]
        return {
            "name": first._get_contract_name() if len(self) == 1 else _("%s + %s ĐNMH") % (first.name, len(self) - 1),
            "partner_id": first.partner_id.id,
            "company_id": first.company_id.id,
            "currency_id": first.currency_id.id,
            "quantity_uom_id": first_uom.id if first_uom else False,
            "note": self._build_contract_note(),
            "line_ids": [command for rec in self for command in rec._prepare_contract_line_commands()],
        }

    def action_view_contract(self):
        self.ensure_one()
        if not self.contract_id:
            raise UserError(_("Đề nghị mua hàng này chưa được chuyển sang hợp đồng."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "contract",
            "view_mode": "form",
            "res_id": self.contract_id.id,
            "target": "current",
        }

    def action_import_lines_excel(self):
        """Mở wizard import custom cho purchase.offer.line."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.offer.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_offer_id": self.id},
        }

    def action_download_template(self):
        """Tải template Excel mẫu cho purchase.offer.line."""
        self.ensure_one()
        from ..wizard.purchase_offer_import_wizard import PurchaseOfferImportWizard
        content = PurchaseOfferImportWizard.generate_template()
        attachment = self.env["ir.attachment"].create({
            "name": "Template_DNMH.xlsx",
            "type": "binary",
            "datas": base64.b64encode(content),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % attachment.id,
            "target": "self",
        }

    def _schedule_reminder_activity(self, deadline, summary, note):
        self.ensure_one()
        if not self.purchaser_id:
            return
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id(self._name)
        existing = self.env["mail.activity"].search_count([
            ("res_model_id", "=", model_id),
            ("res_id", "=", self.id),
            ("activity_type_id", "=", activity_type.id),
            ("user_id", "=", self.purchaser_id.id),
            ("summary", "=", summary),
            ("date_deadline", "=", deadline),
        ])
        if not existing:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=self.purchaser_id.id,
                date_deadline=deadline,
                summary=summary,
                note=note,
            )

    def _send_alert_email(self, subject, body_html):
        self.ensure_one()
        email_to = self.purchaser_id.partner_id.email
        if not email_to:
            return
        self.env["mail.mail"].sudo().create({
            "subject": subject,
            "body_html": body_html,
            "email_to": email_to,
            "auto_delete": True,
        }).send()

    @api.model
    def _cron_process_reminders(self):
        today = fields.Date.context_today(self)
        remind_until = fields.Date.add(today, days=1)
        active_states = ("draft", "waiting_approval", "approved")
        records = self.search([("state", "in", active_states)])
        for rec in records:
            if rec.follow_up_date and not rec.followup_alert_sent and rec.follow_up_date <= remind_until:
                try:
                    summary = _("Đến hạn theo dõi đề nghị mua hàng")
                    note = _("Đề nghị mua hàng %s cần theo dõi với nhà cung cấp %s.") % (
                        rec.display_name, rec.partner_id.display_name
                    )
                    rec._schedule_reminder_activity(rec.follow_up_date, summary, note)
                    rec._send_alert_email(
                        _("Nhắc theo dõi đề nghị mua hàng %s") % rec.display_name,
                        _(
                            "<p>Đề nghị mua hàng <strong>%s</strong> đã đến ngày theo dõi.</p>"
                            "<p>Nhà cung cấp: %s</p>"
                        ) % (rec.display_name, rec.partner_id.display_name),
                    )
                    rec.followup_alert_sent = True
                except Exception as e:
                    _logger.error("Lỗi xử lý reminder cho %s: %s", rec.display_name, e)


class PurchaseOfferLine(models.Model):
    _name = "purchase.offer.line"
    _description = "Dòng đề nghị mua hàng"
    _order = "id"

    offer_id = fields.Many2one("purchase.offer", string="Đề nghị mua hàng", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Sản phẩm", required=True)
    taxes_id = fields.Many2many("account.tax", string="Thuế",
                                domain=[('type_tax_use', '=', 'purchase')])
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Mẫu sản phẩm",
        related="product_id.product_tmpl_id",
        store=True,
        readonly=True,
    )
    description = fields.Char(string="Mô tả")
    uom_id = fields.Many2one("uom.uom", string="Đơn vị tính", required=True)
    quantity = fields.Float(string="Số lượng dự kiến", required=True, digits="Product Unit of Measure")
    qty_received = fields.Float(string="SL đã nhận", digits="Product Unit of Measure", default=0.0)
    expected_price = fields.Monetary(string="Giá dự kiến", required=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", related="offer_id.currency_id", store=True, readonly=True)
    subtotal = fields.Monetary(
        string="Thành tiền dự kiến",
        compute="_compute_subtotal",
        store=True,
        currency_field="currency_id",
    )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.description = line.product_id.display_name
                line.uom_id = line.product_id.uom_po_id.id or line.product_id.uom_id.id
                line.taxes_id = line.product_id.supplier_taxes_id

    @api.depends("quantity", "expected_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.expected_price

    @api.constrains("quantity", "expected_price")
    def _check_positive_values(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Số lượng dự kiến phải lớn hơn 0."))
            if line.expected_price < 0:
                raise ValidationError(_("Giá dự kiến không được âm."))
