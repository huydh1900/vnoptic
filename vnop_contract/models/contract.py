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
        string="Đơn mua hàng",
        domain="[('partner_id','=', partner_id), ('state','in',('purchase','done'))]",
    )
    purchase_order_count = fields.Integer(string="Số PO", compute="_compute_purchase_order_count")
    receipt_ids = fields.One2many("stock.picking", "contract_id", string="Phiếu nhập kho", readonly=True)
    receipt_count_open = fields.Integer(compute="_compute_receipt_metrics", string="Phiếu nhập kho đang mở")
    receipt_count_done = fields.Integer(compute="_compute_receipt_metrics", string="Phiếu nhập kho hoàn tất")
    batch_ids = fields.One2many("stock.picking.batch", "contract_id", string="Lô phiếu nhập kho", readonly=True)
    batch_count = fields.Integer(compute="_compute_batch_count", string="Số lô")
    otk_picking_ids = fields.One2many(
        "stock.picking",
        "contract_id",
        string="Phiếu chuyển OTK",
        domain=[("otk_type", "in", ("ok", "ng"))],
        readonly=True,
    )
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

    # @api.depends("line_ids", "line_ids.product_qty", "line_ids.price_subtotal")
    # def _compute_totals(self):
    #     for rec in self:
    #         rec.total_qty = sum(rec.line_ids.mapped("product_qty"))
    #         rec.amount_total = sum(rec.line_ids.mapped("price_subtotal"))

    def _compute_purchase_order_count(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)

    def _compute_batch_count(self):
        for rec in self:
            rec.batch_count = len(rec.batch_ids)

    def _compute_otk_count(self):
        for rec in self:
            rec.otk_count = len(rec.otk_picking_ids)

    def _compute_receipt_metrics(self):
        for rec in self:
            incoming = rec.receipt_ids.filtered(lambda p: p.picking_type_code == 'incoming')
            rec.receipt_count_open = len(incoming.filtered(lambda p: p.state not in ('done', 'cancel')))
            rec.receipt_count_done = len(incoming.filtered(lambda p: p.state == 'done'))

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
                        "qty_contract": qty_remaining,
                        "qty_remaining": qty_remaining,
                        "price_unit": line.price_unit,
                        "amount_total": line.price_subtotal,
                        "purchase_id": po.id,
                    }))

            contract.line_ids = line_commands

    @api.constrains("purchase_order_ids", "partner_id", "currency_id", "incoterm_id")
    def _check_purchase_order_policy(self):
        for contract in self:
            for po in contract.purchase_order_ids:
                if po.company_id != contract.company_id:
                    raise ValidationError(_("PO %s khác công ty với hợp đồng.") % po.display_name)
                if po.state == 'cancel':
                    raise ValidationError(_("PO %s đang ở trạng thái hủy, không thể thêm vào hợp đồng.") % po.display_name)
                if po.currency_id != contract.currency_id:
                    raise ValidationError(_("PO %s khác tiền tệ với hợp đồng.") % po.display_name)
                if contract.incoterm_id and po.incoterm_id and po.incoterm_id != contract.incoterm_id:
                    raise ValidationError(_("PO %s khác Incoterm với hợp đồng.") % po.display_name)
                if po.contract_id and po.contract_id != contract:
                    raise ValidationError(_("PO %s đã thuộc hợp đồng %s.") % (po.display_name, po.contract_id.display_name))

    def write(self, vals):
        tracked_po_before = {rec.id: rec.purchase_order_ids for rec in self}
        res = super().write(vals)
        if "purchase_order_ids" in vals:
            for contract in self:
                before = tracked_po_before.get(contract.id, self.env['purchase.order'])
                after = contract.purchase_order_ids
                added = after - before
                removed = before - after
                if added:
                    added.write({"contract_id": contract.id})
                    contract._propagate_contract_to_receipts(added)
                if removed:
                    contract._check_po_removal_policy(removed)
                    removed.write({"contract_id": False})
                    contract._clear_contract_on_receipts(removed)
        return res

    def _check_po_removal_policy(self, orders):
        for po in orders:
            done_receipts = po.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming' and p.state == 'done')
            if done_receipts:
                raise UserError(_("Không thể gỡ PO %s vì đã có phiếu nhập kho hoàn tất.") % po.display_name)

    def _propagate_contract_to_receipts(self, orders=None):
        for contract in self:
            purchase_orders = orders or contract.purchase_order_ids
            receipts = purchase_orders.mapped('picking_ids').filtered(
                lambda p: p.picking_type_code == 'incoming' and p.state not in ('done', 'cancel')
            )
            receipts.write({"contract_id": contract.id})
            receipts.move_ids_without_package.write({"contract_id": contract.id})

    def _clear_contract_on_receipts(self, orders):
        receipts = orders.mapped('picking_ids').filtered(
            lambda p: p.picking_type_code == 'incoming' and p.state not in ('done', 'cancel')
        )
        receipts.write({"contract_id": False})
        receipts.move_ids_without_package.write({"contract_id": False})

    def action_propagate_receipt(self):
        self._propagate_contract_to_receipts()

    def action_view_receipts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Phiếu nhập kho"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id), ("picking_type_code", "=", "incoming")],
            "context": {"default_contract_id": self.id},
        }

    def action_view_batches(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lô phiếu nhập kho"),
            "res_model": "stock.picking.batch",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
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

    def action_create_batch_receipt(self):
        self.ensure_one()
        incoming = self.purchase_order_ids.mapped('picking_ids').filtered(
            lambda p: p.picking_type_code == 'incoming'
            and p.state in ('waiting', 'confirmed', 'assigned')
            and not p.batch_id
            and p.state not in ('done', 'cancel')
        )
        if not incoming:
            raise UserError(_("Không có phiếu nhập kho phù hợp để tạo lô."))
        batch = self.env['stock.picking.batch'].create({
            "company_id": self.company_id.id,
            "contract_id": self.id,
            "picking_ids": [(6, 0, incoming.ids)],
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking.batch",
            "view_mode": "form",
            "res_id": batch.id,
            "target": "current",
        }

    def action_create_otk(self):
        self.ensure_one()
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id.company_id', '=', self.company_id.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_("Không tìm thấy loại vận chuyển nội bộ để tạo OTK."))

        temp_location = picking_type.default_location_src_id
        location_ok = self.env['stock.location'].search([
            ('usage', '=', 'internal'), ('company_id', 'in', [self.company_id.id, False]), ('name', 'ilike', 'đạt')
        ], limit=1) or self.env['stock.location'].search([
            ('complete_name', 'ilike', 'OK'), ('usage', '=', 'internal'), ('company_id', 'in', [self.company_id.id, False])
        ], limit=1)
        location_ng = self.env['stock.location'].search([
            ('usage', '=', 'internal'), ('company_id', 'in', [self.company_id.id, False]), ('name', 'ilike', 'NG')
        ], limit=1)
        if not temp_location or not location_ok or not location_ng:
            raise UserError(_("Thiếu cấu hình kho tạm/Kho đạt/Kho NG."))

        grouped = self._get_otk_candidate_quantities(temp_location)
        if not grouped:
            raise UserError(_("Không có số lượng tồn ở kho tạm để OTK."))

        ok_picking = self._create_otk_picking(picking_type, temp_location, location_ok, grouped, "ok")
        ng_picking = self._create_otk_picking(picking_type, temp_location, location_ng, grouped, "ng", create_moves=False)
        return {
            "type": "ir.actions.act_window",
            "name": _("Phiếu chuyển OTK"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", (ok_picking | ng_picking).ids)],
        }

    def _get_otk_candidate_quantities(self, temp_location):
        self.ensure_one()
        incoming_moves = self.env['stock.move'].search([
            ('contract_id', '=', self.id),
            ('state', '=', 'done'),
            ('picking_type_id.code', '=', 'incoming'),
            ('location_dest_id', '=', temp_location.id),
        ])
        if not incoming_moves:
            return {}
        moved = {}
        for move in incoming_moves:
            moved[move.product_id] = moved.get(move.product_id, 0.0) + move.quantity

        otk_done = self.env['stock.move'].search([
            ('contract_id', '=', self.id),
            ('state', '=', 'done'),
            ('picking_id.otk_type', 'in', ('ok', 'ng')),
            ('location_id', '=', temp_location.id),
        ])
        for move in otk_done:
            moved[move.product_id] = moved.get(move.product_id, 0.0) - move.quantity

        return {product: qty for product, qty in moved.items() if qty > 0}

    def _create_otk_picking(self, picking_type, source, destination, grouped, otk_type, create_moves=True):
        self.ensure_one()
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': self.partner_id.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'contract_id': self.id,
            'otk_type': otk_type,
        })
        if create_moves:
            for product, qty in grouped.items():
                self.env['stock.move'].create({
                    'name': product.display_name,
                    'product_id': product.id,
                    'product_uom_qty': qty,
                    'product_uom': product.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': source.id,
                    'location_dest_id': destination.id,
                    'contract_id': self.id,
                })
            picking.action_confirm()
            picking.action_assign()
        return picking

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
