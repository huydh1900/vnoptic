from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class ContractOtk(models.Model):
    _name = "contract.otk"
    _description = "OTK Session"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"))
    contract_id = fields.Many2one("contract", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("done", "Done"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, index=True)

    source_location_id = fields.Many2one("stock.location", required=True)
    ok_location_id = fields.Many2one("stock.location", required=True)
    ng_location_id = fields.Many2one("stock.location", required=True)
    picking_type_id = fields.Many2one("stock.picking.type", required=True)

    picking_ok_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    picking_ng_id = fields.Many2one("stock.picking", readonly=True, copy=False)

    line_ids = fields.One2many("contract.otk.line", "otk_id", copy=False)

    total_checked = fields.Float(compute="_compute_totals", store=True)
    total_ok = fields.Float(compute="_compute_totals", store=True)
    total_ng = fields.Float(compute="_compute_totals", store=True)

    _sql_constraints = [
        ("name_company_unique", "unique(name, company_id)", "OTK number must be unique per company."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = seq.next_by_code("contract.otk.seq") or _("New")
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
            raise ValidationError(_("Product %s requires lot/serial breakdown.") % line.product_id.display_name)
        checked_sum = sum(line.lot_line_ids.mapped("qty_checked"))
        ok_sum = sum(line.lot_line_ids.mapped("qty_ok"))
        if not fields.Float.is_zero(checked_sum - line.qty_checked, precision_rounding=line.uom_id.rounding):
            raise ValidationError(_("Lot checked quantity must equal checked quantity for %s.") % line.product_id.display_name)
        if not fields.Float.is_zero(ok_sum - line.qty_ok, precision_rounding=line.uom_id.rounding):
            raise ValidationError(_("Lot OK quantity must equal OK quantity for %s.") % line.product_id.display_name)

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
                raise UserError(_("Please input at least one line with checked or OK quantity."))

            for line in lines:
                line._check_business_rules()
                rec._validate_tracking_lines(line)
                available_now = line._get_available_qty_temp()
                if line.qty_checked > available_now:
                    raise ValidationError(_("Checked qty for %s exceeds available temporary stock.") % line.product_id.display_name)

            picking_ok = StockPicking.create(rec._prepare_picking_vals("ok"))
            picking_ng = StockPicking.create(rec._prepare_picking_vals("ng"))

            for line in lines:
                if line.qty_ok > 0:
                    move_ok = StockMove.create(line._prepare_move_vals(picking_ok, line.qty_ok, rec.ok_location_id))
                    if line.product_id.tracking != "none":
                        for lot_line in line.lot_line_ids.filtered(lambda l: l.qty_ok > 0):
                            StockMoveLine.create(line._prepare_move_line_vals(move_ok, lot_line.qty_ok, lot_line.lot_id, done_field))
                if line.qty_ng > 0:
                    move_ng = StockMove.create(line._prepare_move_vals(picking_ng, line.qty_ng, rec.ng_location_id))
                    if line.product_id.tracking != "none":
                        for lot_line in line.lot_line_ids.filtered(lambda l: l.qty_ng > 0):
                            StockMoveLine.create(line._prepare_move_line_vals(move_ng, lot_line.qty_ng, lot_line.lot_id, done_field))

            for picking in (picking_ok, picking_ng):
                if picking.move_ids_without_package:
                    picking.action_confirm()
                    picking.action_assign()

            rec.write({
                "state": "confirmed",
                "picking_ok_id": picking_ok.id,
                "picking_ng_id": picking_ng.id,
            })
            rec._update_done_state()
        return True

    def _update_done_state(self):
        for rec in self:
            if rec.state in ("cancel", "done"):
                continue
            if rec.picking_ok_id.state == "done" and rec.picking_ng_id.state == "done":
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
                raise UserError(_("Done OTK session cannot be cancelled."))
            rec.state = "cancel"


class ContractOtkLine(models.Model):
    _name = "contract.otk.line"
    _description = "OTK Session Line"

    otk_id = fields.Many2one("contract.otk", required=True, ondelete="cascade")
    contract_id = fields.Many2one(related="otk_id.contract_id", store=True, index=True)
    purchase_line_id = fields.Many2one("purchase.order.line", required=True)
    purchase_id = fields.Many2one(related="purchase_line_id.order_id", store=True)
    product_id = fields.Many2one(related="purchase_line_id.product_id", store=True)
    uom_id = fields.Many2one(related="purchase_line_id.product_uom", store=True)
    contract_line_id = fields.Many2one("contract.line")
    qty_contract = fields.Float()

    qty_available_temp = fields.Float(compute="_compute_qty_available_temp")
    qty_checked = fields.Float(default=0.0)
    qty_ok = fields.Float(default=0.0)
    qty_ng = fields.Float(compute="_compute_qty_ng", store=True)

    qty_checked_total_before = fields.Float(compute="_compute_totals_before_after")
    qty_ok_total_before = fields.Float(compute="_compute_totals_before_after")
    qty_ng_total_before = fields.Float(compute="_compute_totals_before_after")
    qty_checked_total_after = fields.Float(compute="_compute_totals_before_after")
    qty_short = fields.Float(compute="_compute_totals_before_after")
    qty_excess = fields.Float(compute="_compute_totals_before_after")

    lot_line_ids = fields.One2many("contract.otk.line.lot", "otk_line_id", copy=False)

    @api.depends("qty_checked", "qty_ok")
    def _compute_qty_ng(self):
        for rec in self:
            rec.qty_ng = rec.qty_checked - rec.qty_ok

    def _get_available_qty_temp(self):
        self.ensure_one()
        domain = [
            ("location_id", "=", self.otk_id.source_location_id.id),
            ("product_id", "=", self.product_id.id),
        ]
        if self.product_id.tracking != "none" and self.lot_line_ids:
            domain.append(("lot_id", "in", self.lot_line_ids.mapped("lot_id").ids))
        quants = self.env["stock.quant"].search(domain)
        return sum(quants.mapped(lambda q: q.quantity - q.reserved_quantity))

    @api.depends("otk_id.source_location_id", "product_id", "lot_line_ids")
    def _compute_qty_available_temp(self):
        for rec in self:
            rec.qty_available_temp = rec._get_available_qty_temp() if rec.product_id else 0.0

    @api.depends("purchase_line_id", "otk_id.date", "qty_checked", "qty_contract")
    def _compute_totals_before_after(self):
        for line in self:
            done_lines = self.search([
                ("id", "!=", line.id),
                ("contract_id", "=", line.contract_id.id),
                ("purchase_line_id", "=", line.purchase_line_id.id),
                ("otk_id.state", "=", "done"),
            ])
            checked_before = sum(done_lines.mapped("qty_checked"))
            ok_before = sum(done_lines.mapped("qty_ok"))
            ng_before = sum(done_lines.mapped("qty_ng"))
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
                raise ValidationError(_("Checked/OK quantity cannot be negative."))
            if line.qty_ok > line.qty_checked:
                raise ValidationError(_("OK quantity cannot exceed checked quantity."))

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
    _description = "OTK line lot split"

    otk_line_id = fields.Many2one("contract.otk.line", required=True, ondelete="cascade")
    lot_id = fields.Many2one("stock.lot", required=True)
    qty_checked = fields.Float(default=0.0)
    qty_ok = fields.Float(default=0.0)
    qty_ng = fields.Float(compute="_compute_qty_ng", store=True)

    @api.depends("qty_checked", "qty_ok")
    def _compute_qty_ng(self):
        for rec in self:
            rec.qty_ng = rec.qty_checked - rec.qty_ok

    @api.constrains("qty_checked", "qty_ok", "otk_line_id")
    def _check_qty(self):
        for rec in self:
            if rec.qty_checked < 0 or rec.qty_ok < 0:
                raise ValidationError(_("Lot quantities must be >= 0."))
            if rec.qty_ok > rec.qty_checked:
                raise ValidationError(_("Lot OK quantity cannot exceed checked quantity."))
            if rec.otk_line_id.product_id.tracking == "serial":
                if rec.qty_checked not in (0.0, 1.0) or rec.qty_ok not in (0.0, 1.0):
                    raise ValidationError(_("Serial tracked lot quantities must be 0 or 1."))
