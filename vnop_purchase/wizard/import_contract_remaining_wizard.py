from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ImportContractRemainingWizard(models.TransientModel):
    _name = "import.contract.remaining.wizard"
    _description = "Load Remaining Purchase Order Quantities"

    contract_id = fields.Many2one("import.contract", string="Target Contract", required=True)
    source_contract_id = fields.Many2one("import.contract", string="Source Contract")
    line_ids = fields.One2many("import.contract.remaining.wizard.line", "wizard_id", string="Remaining Lines")

    @api.onchange("source_contract_id")
    def _onchange_source_contract_id(self):
        for wizard in self:
            wizard.line_ids = [(5, 0, 0)]
            domain = [("qty_remaining", ">", 0)]
            if wizard.source_contract_id:
                domain.append(("order_id.import_contract_id", "=", wizard.source_contract_id.id))
            pols = self.env["purchase.order.line"].search(domain)
            wizard.line_ids = [
                (
                    0,
                    0,
                    {
                        "purchase_line_id": line.id,
                        "product_id": line.product_id.id,
                        "remaining_qty": line.qty_remaining,
                        "quantity": line.qty_remaining,
                        "uom_id": line.product_uom.id,
                    },
                )
                for line in pols
            ]

    def action_apply(self):
        self.ensure_one()
        contract_line_vals = []
        for line in self.line_ids.filtered(lambda l: l.quantity > 0):
            if line.quantity > line.remaining_qty:
                raise ValidationError(_("Selected quantity cannot exceed remaining quantity."))
            contract_line_vals.append(
                {
                    "contract_id": self.contract_id.id,
                    "product_id": line.product_id.id,
                    "source_purchase_line_id": line.purchase_line_id.id,
                    "quantity": line.quantity,
                    "uom_id": line.uom_id.id,
                }
            )

        if contract_line_vals:
            self.env["import.contract.line"].create(contract_line_vals)

        return {"type": "ir.actions.act_window_close"}


class ImportContractRemainingWizardLine(models.TransientModel):
    _name = "import.contract.remaining.wizard.line"
    _description = "Remaining Purchase Line"

    wizard_id = fields.Many2one("import.contract.remaining.wizard", required=True, ondelete="cascade")
    purchase_line_id = fields.Many2one("purchase.order.line", string="PO Line", required=True)
    purchase_id = fields.Many2one("purchase.order", related="purchase_line_id.order_id", store=False)
    product_id = fields.Many2one("product.product", string="Product", required=True)
    remaining_qty = fields.Float(string="Remaining Qty", required=True)
    quantity = fields.Float(string="Select Qty", required=True)
    uom_id = fields.Many2one("uom.uom", string="UoM", required=True)

    @api.constrains("quantity", "remaining_qty")
    def _check_quantity(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError(_("Selected quantity must be non-negative."))
            if line.quantity > line.remaining_qty:
                raise ValidationError(_("Selected quantity cannot exceed remaining quantity."))
