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
            ("confirmed_arrival", "Xác nhận hàng về"),
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
        # required=True,
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
    shipment_date = fields.Date(string="Ngày dự kiến giao hàng")
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
    terms = fields.Html(string="Điều khoản & điều kiện")
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
        "contract_purchase_order_rel",
        "contract_id",
        "purchase_order_id",
        string="Đơn mua hàng",
        domain="[('partner_id','=', partner_id), ('state','in',('purchase','done'))]",
    )
    purchase_order_count = fields.Integer(string="Số PO", compute="_compute_purchase_order_count")
    receipt_ids = fields.One2many("stock.picking", "contract_id", string="Phiếu nhập kho", readonly=True)
    receipt_count_open = fields.Integer(compute="_compute_receipt_metrics", string="Số phiếu nhập kho")
    otk_picking_ids = fields.One2many(
        "stock.picking",
        "contract_id",
        string="Phiếu chuyển OTK",
        domain=[("otk_type", "in", ("ok", "ng"))],
        readonly=True,
    )
    otk_session_ids = fields.One2many("contract.otk", "contract_id", string="Lần OTK", readonly=True)
    otk_session_count = fields.Integer(compute="_compute_otk_session_count", string="Số Lần OTK")
    otk_count = fields.Integer(compute="_compute_otk_count", string="Số phiếu OTK")

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

    def _compute_purchase_order_count(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)

    def _compute_otk_count(self):
        for rec in self:
            rec.otk_count = len(rec.otk_picking_ids)

    def _compute_otk_session_count(self):
        for rec in self:
            rec.otk_session_count = len(rec.otk_session_ids)

    @api.depends("purchase_order_ids", "purchase_order_ids.picking_ids", "purchase_order_ids.picking_ids.state",
                 "receipt_ids", "receipt_ids.state")
    def _compute_receipt_metrics(self):
        StockPicking = self.env["stock.picking"]
        for rec in self:
            incoming_done = StockPicking.search_count([
                ("contract_id", "=", rec.id),
                ("picking_type_code", "=", "incoming"),
                ("state", "=", "done"),
            ])
            rec.receipt_count_open = incoming_done

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
            rec.write({"state": "cancel", "delivery_state": "cancel"})

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
                raise ValidationError(_("Ngày dự kiến giao hàng không được để trống!"))
            rec._check_fifo_valuation()
            rec.write({'state': 'waiting'})

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        self.partner_ref = self.partner_id.ref
        self.purchase_order_ids = [(5, 0, 0)]
        self.line_ids = [(5, 0, 0)]

    @api.onchange("purchase_order_ids")
    def _onchange_purchase_order_ids_build_product_lines(self):
        """Tự động nạp dòng sản phẩm từ PO, chỉ đề xuất phần còn lại chưa nhận."""
        for contract in self:
            line_commands = [(5, 0, 0)]

            for po in contract.purchase_order_ids:
                for line in po.order_line:
                    if not line.product_id or line.display_type:
                        continue

                    qty_remaining = max(line.qty_remaining, 0.0)
                    if qty_remaining <= 0:
                        continue

                    line_commands.append((0, 0, {
                        "product_id": line.product_id.id,
                        "uom_id": line.product_uom.id,
                        "currency_id": po.currency_id.id,
                        "product_qty": line.product_qty,
                        "qty_received": line.qty_received,
                        "qty_contract": qty_remaining,
                        "qty_remaining": qty_remaining,
                        "price_unit": line.price_unit,
                        "amount_total": line.price_subtotal,
                        "purchase_id": po.id,
                        "purchase_line_id": line.id,
                    }))

            contract.line_ids = line_commands

    def action_view_receipts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Phiếu nhập kho"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [
                ("contract_id", "=", self.id),
                ("picking_type_code", "=", "incoming"),
                ("state", "=", "done"),
            ],
            "context": {"default_contract_id": self.id},
        }

    def action_view_otk(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Phiếu chuyển OTK"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id), ("otk_type", "in", ("ok", "ng"))],
            "context": {"default_contract_id": self.id},
        }

    def action_view_otk_sessions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lần OTK"),
            "res_model": "contract.otk",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "context": {"default_contract_id": self.id},
        }

    def _get_default_otk_configuration(self):
        self.ensure_one()
        company = self.company_id
        source = company.otk_source_location_id
        internal_picking_type = company.otk_internal_picking_type_id

        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("company_id", "=", company.id),
        ], limit=1)
        source = source or incoming_type.default_location_dest_id

        internal_picking_type = internal_picking_type or self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("company_id", "=", company.id),
        ], limit=1)
        return source, company.otk_ok_location_id, company.otk_ng_location_id, internal_picking_type

    def action_create_otk_session(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Chỉ tạo OTK khi hợp đồng đã duyệt."))

        source, ok_location, ng_location, picking_type = self._get_default_otk_configuration()
        if not source or not ok_location or not ng_location or not picking_type:
            raise UserError(_("Thiếu cấu hình OTK mặc định trên công ty (source/OK/NG/picking type)."))

        lines = self.line_ids.filtered(lambda l: l.purchase_line_id and l.qty_contract > 0)
        if not lines:
            raise UserError(_("Hợp đồng không có dòng PO hợp lệ để tạo OTK."))

        session = self.env["contract.otk"].create({
            "contract_id": self.id,
            "company_id": self.company_id.id,
            "source_location_id": source.id,
            "ok_location_id": ok_location.id,
            "ng_location_id": ng_location.id,
            "picking_type_id": picking_type.id,
            "line_ids": [(0, 0, {
                "purchase_line_id": line.purchase_line_id.id,
                "contract_line_id": line.id,
                "qty_contract": line.qty_contract,
            }) for line in lines],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Lần OTK"),
            "res_model": "contract.otk",
            "view_mode": "form",
            "res_id": session.id,
            "target": "current",
        }

    def action_confirm_arrival_auto(self):
        self.ensure_one()
        self._process_contract_receipts()
        self._update_delivery_state_from_receipts()

    def _update_delivery_state_from_receipts(self):
        for rec in self:
            if rec.state == "cancel" or rec.delivery_state == "cancel":
                rec.delivery_state = "cancel"
                continue

            contract_lines = rec.line_ids.filtered(lambda l: l.purchase_line_id and l.qty_contract > 0)
            done_incoming_count = self.env["stock.picking"].search_count([
                ("contract_id", "=", rec.id),
                ("picking_type_code", "=", "incoming"),
                ("state", "=", "done"),
            ])

            if not contract_lines:
                rec.delivery_state = "confirmed_arrival" if done_incoming_count else "expected"
                continue

            all_received = all(line.qty_received >= line.qty_contract for line in contract_lines)
            any_received = any(line.qty_received > 0 for line in contract_lines)

            if all_received:
                new_state = "done"
            elif any_received:
                new_state = "partial"
            elif done_incoming_count:
                new_state = "confirmed_arrival"
            else:
                new_state = "expected"

            rec.delivery_state = new_state

    def _process_contract_receipts(self):
        """
        Validate receipt theo qty_contract nhưng backorder phải sinh ra chuẩn Odoo.
        Quy tắc:
          - KHÔNG sửa demand (product_uom_qty) theo hợp đồng
          - CHỈ set qty_done = qty_contract (nhận thiếu so với demand) => Odoo bắt wizard backorder
          - Tự process wizard backorder để sinh phiếu backorder (kiểm soát chặt)
        """
        self.ensure_one()

        qty_by_purchase_line = {
            line.purchase_line_id.id: (line.qty_contract or 0.0)
            for line in self.line_ids.filtered("purchase_line_id")
            if (line.qty_contract or 0.0) > 0
        }
        if not qty_by_purchase_line:
            return

        candidate_pickings = self.purchase_order_ids.picking_ids.filtered(
            lambda p: p.state not in ("done", "cancel") and p.picking_type_code == "incoming"
        )
        if not candidate_pickings:
            return

        for picking in candidate_pickings:
            # gắn contract cho picking/move để trace
            picking.write({"contract_id": self.id})
            picking.move_ids_without_package.write({"contract_id": self.id})

            moves_to_receive = picking.move_ids_without_package.filtered(
                lambda m: m.purchase_line_id and m.purchase_line_id.id in qty_by_purchase_line
            )
            if not moves_to_receive:
                continue

            # confirm/assign trước khi set done
            if picking.state == "draft":
                picking.action_confirm()
            if picking.state in ("confirmed", "waiting"):
                picking.action_assign()

            # set qty_done theo hợp đồng (nhưng không vượt demand còn lại)
            for move in moves_to_receive:
                qty_contract = qty_by_purchase_line.get(move.purchase_line_id.id, 0.0)

                # chặn lot/serial
                if move.product_id.tracking in ("lot", "serial"):
                    raise UserError(_(
                        "Sản phẩm %s yêu cầu Lot/Serial. Không thể auto nhận/backorder.\n"
                        "Vui lòng nhập Lot/Serial trong Hoạt động chi tiết."
                    ) % move.product_id.display_name)

                # giới hạn để không vượt demand còn lại của move
                move_remaining = self._get_move_remaining_qty(move)
                qty_done = min(qty_contract, move_remaining)
                if qty_done <= 0:
                    continue

                self._set_done_qty_for_move(move, qty_done)

            # validate => Odoo sẽ trả wizard backorder nếu có nhận thiếu
            validate_result = picking.button_validate()

            # Tự xử lý wizard backorder/immediate transfer (nếu có)
            self._auto_process_validate_result(validate_result)

    def _set_done_qty_for_move(self, move, qty_done):
        """
        Set qty_done cho move bằng move lines.
        - Nếu đã có move line -> dồn vào line đầu (reset các line khác về 0)
        - Nếu chưa có -> tạo 1 move line mới
        """
        MoveLine = self.env["stock.move.line"]
        done_field = "qty_done" if "qty_done" in MoveLine._fields else "quantity"

        if move.move_line_ids:
            # reset
            for ml in move.move_line_ids:
                ml[done_field] = 0.0
            move.move_line_ids[0][done_field] = qty_done
            return

        MoveLine.create({
            "picking_id": move.picking_id.id,
            "move_id": move.id,
            "product_id": move.product_id.id,
            "product_uom_id": move.product_uom.id,
            "location_id": move.location_id.id,
            "location_dest_id": move.location_dest_id.id,
            done_field: qty_done,
        })

    def _get_move_remaining_qty(self, move):
        """
        Remaining demand của move = product_uom_qty - done
        (để không set qty_done vượt quá phần còn lại)
        """
        done_qty = 0.0
        if "quantity_done" in move._fields:
            done_qty = move.quantity_done or 0.0
        else:
            MoveLine = self.env["stock.move.line"]
            done_field = "qty_done" if "qty_done" in MoveLine._fields else "quantity"
            done_qty = sum(move.move_line_ids.mapped(done_field)) or 0.0

        return max((move.product_uom_qty or 0.0) - done_qty, 0.0)

    def _auto_process_validate_result(self, action_result):
        """
        Tự process wizard trả về từ button_validate để không hỏi user.
        Backorder: stock.backorder.confirmation -> process()
        Immediate transfer: stock.immediate.transfer -> process()
        """
        if not action_result or not isinstance(action_result, dict):
            return

        res_model = action_result.get("res_model")
        res_id = action_result.get("res_id")
        if not res_model or not res_id:
            return

        wizard = self.env[res_model].browse(res_id)

        if res_model == "stock.backorder.confirmation":
            wizard.process()
            return

        if res_model == "stock.immediate.transfer":
            wizard.process()
            return

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
