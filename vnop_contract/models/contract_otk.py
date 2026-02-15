from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class ContractOtk(models.Model):
    _name = "contract.otk"
    _description = "Lần kiểm tra chất lượng (OTK)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Số phiếu OTK",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("Mới")
    )

    contract_id = fields.Many2one(
        "contract",
        string="Hợp đồng",
        required=True,
        ondelete="cascade",
        index=True
    )

    otk_sequence = fields.Integer(
        string="Lần OTK",
        readonly=True,
        copy=False,
        index=True,
    )

    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company
    )

    date = fields.Datetime(
        string="Ngày kiểm tra",
        required=True,
        default=fields.Datetime.now,
        tracking=True
    )

    state = fields.Selection([
        ("draft", "Nháp"),
        ("confirmed", "Đã xác nhận"),
        ("done", "Hoàn tất"),
        ("cancel", "Đã hủy"),
    ],
        string="Trạng thái",
        default="draft",
        tracking=True,
        index=True
    )

    source_location_id = fields.Many2one(
        "stock.location",
        string="Vị trí nguồn (Kho chờ kiểm)",
        required=True,
    )

    ok_location_id = fields.Many2one(
        "stock.location",
        string="Vị trí đạt (Kho OK)",
        required=True,
    )

    ng_location_id = fields.Many2one(
        "stock.location",
        string="Vị trí không đạt (Kho NG)",
        required=True,
    )

    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Loại vận chuyển OTK",
        required=True
    )

    picking_ok_id = fields.Many2one(
        "stock.picking",
        string="Phiếu chuyển kho OK",
        readonly=True,
        copy=False
    )

    picking_ng_id = fields.Many2one(
        "stock.picking",
        string="Phiếu chuyển kho NG",
        readonly=True,
        copy=False
    )

    line_ids = fields.One2many(
        "contract.otk.line",
        "otk_id",
        string="Chi tiết kiểm tra",
        copy=False
    )

    total_checked = fields.Float(
        string="Tổng số lượng đã kiểm",
        compute="_compute_totals",
        store=True
    )

    total_ok = fields.Float(
        string="Tổng số lượng đạt",
        compute="_compute_totals",
        store=True
    )

    total_ng = fields.Float(
        string="Tổng số lượng không đạt",
        compute="_compute_totals",
        store=True
    )

    _sql_constraints = [
        ("name_company_unique", "unique(name, company_id)", "Số OTK phải là duy nhất trong từng công ty."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        contract_ids = [vals.get("contract_id") for vals in vals_list if vals.get("contract_id")]
        next_seq_by_contract = {}
        if contract_ids:
            grouped = self.read_group(
                [("contract_id", "in", contract_ids)],
                ["contract_id", "otk_sequence:max"],
                ["contract_id"],
            )
            next_seq_by_contract = {
                data["contract_id"][0]: (data.get("otk_sequence_max") or 0) + 1
                for data in grouped
                if data.get("contract_id")
            }
        for vals in vals_list:
            if vals.get("name", _("Mới")) == _("Mới"):
                vals["name"] = seq.next_by_code("contract.otk.seq") or _("Mới")
            if vals.get("contract_id") and not vals.get("otk_sequence"):
                contract_id = vals["contract_id"]
                vals["otk_sequence"] = next_seq_by_contract.get(contract_id, 1)
                next_seq_by_contract[contract_id] = vals["otk_sequence"] + 1
        return super().create(vals_list)

    @api.depends("line_ids.qty_checked", "line_ids.qty_ok", "line_ids.qty_ng")
    def _compute_totals(self):
        for rec in self:
            rec.total_checked = sum(rec.line_ids.mapped("qty_checked"))
            rec.total_ok = sum(rec.line_ids.mapped("qty_ok"))
            rec.total_ng = sum(rec.line_ids.mapped("qty_ng"))

    def _prepare_picking_vals(self, otk_type):
        self.ensure_one()
        dest = self.ok_location_id if otk_type == "ok" else self.ng_location_id
        return {
            "picking_type_id": self.picking_type_id.id,
            "partner_id": self.contract_id.partner_id.id,
            "location_id": self.source_location_id.id,
            "location_dest_id": dest.id,
            "origin": self.name,
            "company_id": self.company_id.id,
            "contract_id": self.contract_id.id,
            "contract_otk_id": self.id,
            "otk_type": otk_type,
        }

    def _validate_tracking_lines(self, line):
        if line.product_id.tracking == "none":
            return
        if not line.lot_line_ids:
            raise ValidationError(
                _("Sản phẩm %s yêu cầu khai báo chi tiết theo lô/serial.") % line.product_id.display_name)
        checked_sum = sum(line.lot_line_ids.mapped("qty_checked"))
        ok_sum = sum(line.lot_line_ids.mapped("qty_ok"))
        if not fields.Float.is_zero(checked_sum - line.qty_checked, precision_rounding=line.uom_id.rounding):
            raise ValidationError(_("Tổng SL kiểm theo lô phải bằng SL kiểm của %s.") % line.product_id.display_name)
        if not fields.Float.is_zero(ok_sum - line.qty_ok, precision_rounding=line.uom_id.rounding):
            raise ValidationError(_("Tổng SL đạt theo lô phải bằng SL đạt của %s.") % line.product_id.display_name)

    def action_confirm(self):
        StockPicking = self.env["stock.picking"]
        StockMove = self.env["stock.move"]
        StockMoveLine = self.env["stock.move.line"]
        done_field = "qty_done" if "qty_done" in StockMoveLine._fields else "quantity"

        for rec in self:
            if rec.state != "draft":
                continue
            lines = rec.line_ids.filtered(lambda l: l.qty_checked or l.qty_ok)
            if not lines:
                raise UserError(_("Vui lòng nhập ít nhất một dòng có SL kiểm hoặc SL đạt."))

            for line in lines:
                line._lock_related_quants_for_update()
                line._check_business_rules()
                rec._validate_tracking_lines(line)
                available_now = line._get_available_qty_temp()
                if line.qty_checked > available_now:
                    raise ValidationError(_("SL kiểm của %s vượt quá tồn tạm khả dụng.") % line.product_id.display_name)

            has_ok_move = any(line.qty_ok > 0 for line in lines)
            has_ng_move = any(line.qty_ng > 0 for line in lines)
            picking_ok = StockPicking.create(rec._prepare_picking_vals("ok")) if has_ok_move else False
            picking_ng = StockPicking.create(rec._prepare_picking_vals("ng")) if has_ng_move else False

            for line in lines:
                if line.qty_ok > 0:
                    move_ok = StockMove.create(line._prepare_move_vals(picking_ok, line.qty_ok, rec.ok_location_id))
                    if line.product_id.tracking != "none":
                        for lot_line in line.lot_line_ids.filtered(lambda l: l.qty_ok > 0):
                            StockMoveLine.create(
                                line._prepare_move_line_vals(move_ok, lot_line.qty_ok, lot_line.lot_id, done_field))
                if line.qty_ng > 0:
                    move_ng = StockMove.create(line._prepare_move_vals(picking_ng, line.qty_ng, rec.ng_location_id))
                    if line.product_id.tracking != "none":
                        for lot_line in line.lot_line_ids.filtered(lambda l: l.qty_ng > 0):
                            StockMoveLine.create(
                                line._prepare_move_line_vals(move_ng, lot_line.qty_ng, lot_line.lot_id, done_field))

            for picking in (picking_ok, picking_ng):
                if picking:
                    picking.action_confirm()
                    picking.action_assign()

            rec.write({
                "state": "confirmed",
                "picking_ok_id": picking_ok.id if picking_ok else False,
                "picking_ng_id": picking_ng.id if picking_ng else False,
            })
            rec._update_done_state()
        return True

    def _update_done_state(self):
        for rec in self:
            if rec.state in ("cancel", "done"):
                continue
            pickings = (rec.picking_ok_id | rec.picking_ng_id)
            if pickings and all(picking.state == "done" for picking in pickings):
                rec.state = "done"

    def action_open_picking_ok(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_ok_id.id,
            "target": "current",
        }

    def action_open_picking_ng(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_ng_id.id,
            "target": "current",
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == "done":
                raise UserError(_("Lần OTK đã hoàn tất thì không thể hủy."))
            rec.state = "cancel"


class ContractOtkLine(models.Model):
    _name = "contract.otk.line"
    _description = "Line lần OTK"

    otk_id = fields.Many2one("contract.otk", string="Lần OTK", required=True, ondelete="cascade")
    contract_id = fields.Many2one(string="Hợp đồng", related="otk_id.contract_id", store=True, index=True)
    purchase_line_id = fields.Many2one("purchase.order.line", string="Dòng đơn mua", required=True)
    purchase_id = fields.Many2one(string="Đơn mua", related="purchase_line_id.order_id", store=True)
    product_id = fields.Many2one(string="Sản phẩm", related="purchase_line_id.product_id", store=True)
    uom_id = fields.Many2one(string="Đơn vị tính", related="purchase_line_id.product_uom", store=True)
    contract_line_id = fields.Many2one("contract.line", string="Dòng hợp đồng")
    qty_contract = fields.Float(string="Số lượng hợp đồng")

    qty_available_temp = fields.Float(string="Tồn khả dụng tạm", compute="_compute_qty_available_temp")
    qty_checked = fields.Float(string="Số lượng kiểm", default=0.0)
    qty_ok = fields.Float(string="Số lượng đạt", default=0.0)
    qty_ng = fields.Float(string="Số lượng lỗi", compute="_compute_qty_ng", store=True)

    qty_checked_total_before = fields.Float(string="Tổng SL kiểm trước", compute="_compute_totals_before_after")
    qty_ok_total_before = fields.Float(string="Tổng SL đạt trước", compute="_compute_totals_before_after")
    qty_ng_total_before = fields.Float(string="Tổng SL lỗi trước", compute="_compute_totals_before_after")
    qty_checked_total_after = fields.Float(string="Tổng SL kiểm sau", compute="_compute_totals_before_after")
    qty_short = fields.Float(string="Số lượng thiếu", compute="_compute_totals_before_after")
    qty_excess = fields.Float(string="Số lượng thừa", compute="_compute_totals_before_after")

    lot_line_ids = fields.One2many("contract.otk.line.lot", "otk_line_id", copy=False)

    @api.depends("qty_checked", "qty_ok")
    def _compute_qty_ng(self):
        for rec in self:
            rec.qty_ng = rec.qty_checked - rec.qty_ok

    def _get_available_qty_temp(self):
        self.ensure_one()
        quant_model = self.env["stock.quant"]
        if self.product_id.tracking != "none" and self.lot_line_ids:
            return sum(
                quant_model._get_available_quantity(
                    self.product_id,
                    self.otk_id.source_location_id,
                    lot_id=lot_line.lot_id,
                )
                for lot_line in self.lot_line_ids
            )
        return quant_model._get_available_quantity(
            self.product_id,
            self.otk_id.source_location_id,
        )

    def _lock_related_quants_for_update(self):
        self.ensure_one()
        lot_ids = self.lot_line_ids.mapped("lot_id").ids if self.product_id.tracking != "none" else []
        query = """
            SELECT id
            FROM stock_quant
            WHERE location_id = %s
              AND product_id = %s
              AND (%s = false OR lot_id = ANY(%s))
            FOR UPDATE
        """
        self.env.cr.execute(
            query,
            (
                self.otk_id.source_location_id.id,
                self.product_id.id,
                bool(lot_ids),
                lot_ids or [0],
            ),
        )

    @api.depends("otk_id.source_location_id", "product_id", "lot_line_ids")
    def _compute_qty_available_temp(self):
        for rec in self:
            rec.qty_available_temp = rec._get_available_qty_temp() if rec.product_id else 0.0

    @api.depends("purchase_line_id", "otk_id.date", "qty_checked", "qty_contract")
    def _compute_totals_before_after(self):
        key_pairs = {
            (line.contract_id.id, line.purchase_line_id.id)
            for line in self
            if line.contract_id and line.purchase_line_id
        }
        done_grouped = {}
        if key_pairs:
            done_groups = self.read_group(
                [
                    ("contract_id", "in", list({item[0] for item in key_pairs})),
                    ("purchase_line_id", "in", list({item[1] for item in key_pairs})),
                    ("otk_id.state", "=", "done"),
                ],
                ["contract_id", "purchase_line_id", "qty_checked:sum", "qty_ok:sum", "qty_ng:sum"],
                ["contract_id", "purchase_line_id"],
            )
            done_grouped = {
                (item["contract_id"][0], item["purchase_line_id"][0]): {
                    "checked": item.get("qty_checked", 0.0),
                    "ok": item.get("qty_ok", 0.0),
                    "ng": item.get("qty_ng", 0.0),
                }
                for item in done_groups
                if item.get("contract_id") and item.get("purchase_line_id")
            }

        for line in self:
            values = done_grouped.get((line.contract_id.id, line.purchase_line_id.id), {})
            checked_before = values.get("checked", 0.0)
            ok_before = values.get("ok", 0.0)
            ng_before = values.get("ng", 0.0)
            checked_after = checked_before + line.qty_checked
            line.qty_checked_total_before = checked_before
            line.qty_ok_total_before = ok_before
            line.qty_ng_total_before = ng_before
            line.qty_checked_total_after = checked_after
            line.qty_short = max(0.0, line.qty_contract - checked_after)
            line.qty_excess = max(0.0, checked_after - line.qty_contract)

    @api.constrains("qty_checked", "qty_ok")
    def _check_business_rules(self):
        for line in self:
            if line.qty_checked < 0 or line.qty_ok < 0:
                raise ValidationError(_("SL kiểm/SL đạt không được âm."))
            if line.qty_ok > line.qty_checked:
                raise ValidationError(_("SL đạt không được lớn hơn SL kiểm."))

    @api.constrains("lot_line_ids", "product_id", "qty_checked")
    def _check_unique_lot_and_serial(self):
        for line in self:
            if not line.lot_line_ids:
                continue
            lot_ids = line.lot_line_ids.mapped("lot_id").ids
            if len(lot_ids) != len(set(lot_ids)):
                raise ValidationError(_("Không được chọn trùng lô/serial trong cùng một dòng OTK."))
            if line.product_id.tracking == "serial":
                serial_count = len(line.lot_line_ids.filtered("lot_id"))
                if not fields.Float.is_zero(
                    line.qty_checked - serial_count,
                    precision_rounding=line.uom_id.rounding,
                ):
                    raise ValidationError(_("Với sản phẩm serial, SL kiểm phải bằng số serial đã khai báo."))

    def _prepare_move_vals(self, picking, qty, dest_location):
        self.ensure_one()
        return {
            "name": self.product_id.display_name,
            "picking_id": picking.id,
            "product_id": self.product_id.id,
            "product_uom_qty": qty,
            "product_uom": self.uom_id.id,
            "location_id": self.otk_id.source_location_id.id,
            "location_dest_id": dest_location.id,
            "contract_id": self.contract_id.id,
            "contract_otk_line_id": self.id,
        }

    def _prepare_move_line_vals(self, move, qty, lot, done_field):
        self.ensure_one()
        return {
            "picking_id": move.picking_id.id,
            "move_id": move.id,
            "product_id": self.product_id.id,
            "product_uom_id": self.uom_id.id,
            "location_id": move.location_id.id,
            "location_dest_id": move.location_dest_id.id,
            "lot_id": lot.id,
            done_field: qty,
        }


class ContractOtkLineLot(models.Model):
    _name = "contract.otk.line.lot"
    _description = "Chi tiết lô dòng OTK"

    otk_line_id = fields.Many2one("contract.otk.line", required=True, ondelete="cascade")
    lot_id = fields.Many2one("stock.lot", required=True)
    qty_checked = fields.Float(string="Số lượng kiểm", default=0.0)
    qty_ok = fields.Float(string="Số lượng đạt", default=0.0)
    qty_ng = fields.Float(string="Số lượng lỗi", compute="_compute_qty_ng", store=True)

    @api.depends("qty_checked", "qty_ok")
    def _compute_qty_ng(self):
        for rec in self:
            rec.qty_ng = rec.qty_checked - rec.qty_ok

    @api.constrains("qty_checked", "qty_ok", "otk_line_id")
    def _check_qty(self):
        for rec in self:
            if rec.qty_checked < 0 or rec.qty_ok < 0:
                raise ValidationError(_("Số lượng theo lô phải lớn hơn hoặc bằng 0."))
            if rec.qty_ok > rec.qty_checked:
                raise ValidationError(_("SL đạt theo lô không được lớn hơn SL kiểm theo lô."))
            if rec.otk_line_id.product_id.tracking == "serial":
                if rec.qty_checked not in (0.0, 1.0) or rec.qty_ok not in (0.0, 1.0):
                    raise ValidationError(_("Sản phẩm quản lý theo serial chỉ cho phép SL lô là 0 hoặc 1."))
