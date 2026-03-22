# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Contract(models.Model):
    _inherit = "contract"

    purchase_offer_ids = fields.One2many(
        "purchase.offer",
        "contract_id",
        string="Đề nghị mua hàng nguồn",
        readonly=True,
        copy=False,
    )
    approved_purchase_offer_ids = fields.Many2many(
        "purchase.offer",
        compute="_compute_approved_purchase_offer_ids",
        inverse="_inverse_approved_purchase_offer_ids",
        string="Đề nghị mua hàng",
        copy=False,
    )
    purchase_offer_count = fields.Integer(
        string="Số Đề nghị mua hàng",
        compute="_compute_purchase_offer_count",
    )

    @api.depends("purchase_offer_ids")
    def _compute_approved_purchase_offer_ids(self):
        for rec in self:
            rec.approved_purchase_offer_ids = rec.purchase_offer_ids

    def _compute_purchase_offer_count(self):
        for rec in self:
            rec.purchase_offer_count = len(rec.purchase_offer_ids)

    def _validate_selected_purchase_offers(self, purchase_offers):
        for contract in self:
            if contract.state != "draft":
                raise ValidationError(_("Chỉ được chọn Đề nghị mua hàng khi hợp đồng đang ở trạng thái Nháp."))
            if not purchase_offers:
                continue

            invalid_state = purchase_offers.filtered(lambda rec: rec.state not in ("approved", "converted"))
            if invalid_state:
                raise ValidationError(_("Chỉ được chọn các Đề nghị mua hàng đã duyệt."))

            invalid_contract = purchase_offers.filtered(lambda rec: rec.contract_id and rec.contract_id != contract)
            if invalid_contract:
                raise ValidationError(_("Có Đề nghị mua hàng đã thuộc hợp đồng khác."))

            partners = purchase_offers.mapped("partner_id")
            if len(partners) > 1 or (contract.partner_id and partners and partners != contract.partner_id):
                raise ValidationError(_("Tất cả Đề nghị mua hàng phải cùng nhà cung cấp với hợp đồng."))

            companies = purchase_offers.mapped("company_id")
            if len(companies) > 1 or (contract.company_id and companies and companies != contract.company_id):
                raise ValidationError(_("Tất cả Đề nghị mua hàng phải cùng công ty với hợp đồng."))

            currencies = purchase_offers.mapped("currency_id")
            if len(currencies) > 1 or (contract.currency_id and currencies and currencies != contract.currency_id):
                raise ValidationError(_("Tất cả Đề nghị mua hàng phải cùng loại tiền tệ với hợp đồng."))

    def _prepare_contract_line_vals_from_offer_line(self, offer_line):
        return {
            "product_id": offer_line.product_id.id,
            "uom_id": offer_line.uom_id.id,
            "currency_id": offer_line.currency_id.id,
            "product_qty": offer_line.quantity,
            "price_unit": offer_line.expected_price,
            "amount_total": offer_line.subtotal,
            "purchase_offer_line_id": offer_line.id,
        }

    def _sync_contract_lines_from_purchase_offers(self):
        for contract in self:
            selected_offer_lines = contract.purchase_offer_ids.mapped("line_ids")
            selected_ids = set(selected_offer_lines.ids)
            offer_contract_lines = contract.line_ids.filtered("purchase_offer_line_id")

            obsolete_lines = offer_contract_lines.filtered(lambda line: line.purchase_offer_line_id.id not in selected_ids)
            if obsolete_lines:
                obsolete_lines.unlink()

            existing_map = {line.purchase_offer_line_id.id: line for line in contract.line_ids.filtered("purchase_offer_line_id")}
            for offer_line in selected_offer_lines:
                vals = contract._prepare_contract_line_vals_from_offer_line(offer_line)
                existing_line = existing_map.get(offer_line.id)
                if existing_line:
                    existing_line.write(vals)
                else:
                    contract.write({"line_ids": [(0, 0, vals)]})

            if selected_offer_lines and not contract.quantity_uom_id:
                contract.quantity_uom_id = selected_offer_lines[:1].uom_id

    def _inverse_approved_purchase_offer_ids(self):
        for contract in self:
            selected = contract.approved_purchase_offer_ids
            contract._validate_selected_purchase_offers(selected)

            added = selected - contract.purchase_offer_ids
            removed = contract.purchase_offer_ids - selected

            if selected and not contract.partner_id:
                contract.partner_id = selected[:1].partner_id
            if selected and not contract.company_id:
                contract.company_id = selected[:1].company_id
            if selected and not contract.currency_id:
                contract.currency_id = selected[:1].currency_id

            if added:
                added.write({"contract_id": contract.id, "state": "converted"})
            if removed:
                removed.write({"contract_id": False})
                removed.filtered(lambda rec: rec.state == "converted").write({"state": "approved"})

            contract._sync_contract_lines_from_purchase_offers()

    def action_view_purchase_offers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Đề nghị mua hàng nguồn",
            "res_model": "purchase.offer",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "target": "current",
        }
