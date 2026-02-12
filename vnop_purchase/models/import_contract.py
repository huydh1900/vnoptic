from odoo import api, fields, models, _


class ImportContract(models.Model):
    _name = "import.contract"
    _description = "Import Contract"

    name = fields.Char(string="Contract No.", required=True, copy=False, default=lambda self: _("New"))
    partner_id = fields.Many2one("res.partner", string="Vendor", required=True, domain="[('supplier_rank', '>', 0)]")
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one("res.company", string="Company", required=True, default=lambda self: self.env.company)
    incoterm_id = fields.Many2one("account.incoterms", string="Incoterm")
    etd_date = fields.Date(string="ETD")
    eta_date = fields.Date(string="ETA")

    purchase_ids = fields.One2many("purchase.order", "import_contract_id", string="Purchase Orders")
    delivery_schedule_ids = fields.Many2many("delivery.schedule", string="Delivery Schedules")

    order_line_ids = fields.One2many("import.contract.line", "contract_id", string="Contract Lines")

    purchase_count = fields.Integer(compute="_compute_purchase_count")
    qty_ordered_total = fields.Float(string="Total Ordered Qty", compute="_compute_qty_totals")
    qty_received_total = fields.Float(string="Total Received Qty", compute="_compute_qty_totals")
    qty_remaining_total = fields.Float(string="Total Remaining Qty", compute="_compute_qty_totals")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("import.contract") or _("New")
        return super().create(vals_list)

    @api.depends("purchase_ids")
    def _compute_purchase_count(self):
        for contract in self:
            contract.purchase_count = len(contract.purchase_ids)

    @api.depends("purchase_ids.order_line.product_qty", "purchase_ids.order_line.qty_received")
    def _compute_qty_totals(self):
        for contract in self:
            lines = contract.purchase_ids.order_line
            contract.qty_ordered_total = sum(lines.mapped("product_qty"))
            contract.qty_received_total = sum(lines.mapped("qty_received"))
            contract.qty_remaining_total = sum(lines.mapped("qty_remaining"))

    def action_open_purchases(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Orders"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("import_contract_id", "=", self.id)],
            "context": {"default_import_contract_id": self.id},
        }

    def action_open_remaining_lines_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Load Remaining PO Quantities"),
            "res_model": "import.contract.remaining.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_contract_id": self.id,
            },
        }


class ImportContractLine(models.Model):
    _name = "import.contract.line"
    _description = "Import Contract Line"

    contract_id = fields.Many2one("import.contract", string="Contract", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Product", required=True)
    source_purchase_line_id = fields.Many2one("purchase.order.line", string="Source PO Line")
    quantity = fields.Float(string="Quantity", required=True)
    uom_id = fields.Many2one("uom.uom", string="UoM", required=True)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            line.uom_id = line.product_id.uom_po_id or line.product_id.uom_id
