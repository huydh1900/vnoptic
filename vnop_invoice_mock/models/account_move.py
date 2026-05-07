# -*- coding: utf-8 -*-
import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_EINV_MOVE_TYPES = ("out_invoice", "out_refund")


class AccountMove(models.Model):
    _inherit = "account.move"

    mock_einv_symbol = fields.Char(
        string="Ký hiệu HĐ",
        size=8,
        copy=False,
        tracking=True,
    )
    mock_einv_template_no = fields.Char(
        string="Mẫu số",
        size=11,
        default="1/001",
    )
    mock_einv_lookup_code = fields.Char(
        string="Mã tra cứu",
        compute="_compute_mock_einv_lookup_code",
        store=True,
    )
    mock_einv_state = fields.Selection(
        selection=[
            ("not_issued", "Chưa phát hành"),
            ("issued", "Đã phát hành"),
            ("sent", "Đã gửi"),
            ("replaced", "Đã thay thế"),
        ],
        string="Trạng thái HĐĐT",
        default="not_issued",
        tracking=True,
        copy=False,
    )
    mock_einv_issued_at = fields.Datetime(
        string="Ngày phát hành",
        readonly=True,
        copy=False,
    )
    mock_einv_pdf_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="PDF hóa đơn",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    # -------------------------------------------------------------------------
    # Compute
    # -------------------------------------------------------------------------

    @api.depends("name")
    def _compute_mock_einv_lookup_code(self):
        for move in self:
            if move.name and move.name != "/":
                raw = move.name + str(move.id or "")
                move.mock_einv_lookup_code = hashlib.sha1(
                    raw.encode("utf-8")
                ).hexdigest()[:12].upper()
            else:
                move.mock_einv_lookup_code = "/"

    # -------------------------------------------------------------------------
    # Override _post
    # -------------------------------------------------------------------------

    def _post(self, soft=True):
        # Call super first — Odoo 18 standard
        res = super()._post(soft=soft)

        # Issue e-invoice for eligible moves
        for move in self:
            if (
                move.move_type in _EINV_MOVE_TYPES
                and move.mock_einv_state == "not_issued"
            ):
                move._mock_issue_einv()

        return res

    # -------------------------------------------------------------------------
    # Override button_draft — reset mock fields on revert
    # -------------------------------------------------------------------------

    def button_draft(self):
        res = super().button_draft()

        mock_issued = self.filtered(
            lambda m: m.mock_einv_state in ("issued", "sent")
        )
        if mock_issued:
            # Unlink existing PDF attachments
            attachments = mock_issued.mapped("mock_einv_pdf_attachment_id")
            mock_issued.write({
                "mock_einv_state": "not_issued",
                "mock_einv_issued_at": False,
                "mock_einv_pdf_attachment_id": False,
                "mock_einv_symbol": False,
            })
            attachments.sudo().unlink()

        return res

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _mock_issue_einv(self):
        """Phát hành HĐĐT mock: set ký hiệu, thời gian, tạo PDF attachment."""
        self.ensure_one()

        # Generate ký hiệu from sequence (per-company)
        symbol = self.env["ir.sequence"].with_company(
            self.company_id
        ).next_by_code("vnop_invoice_mock.einv_symbol") or "/"

        # Render PDF
        pdf_content, _mime = self.env["ir.actions.report"]._render_qweb_pdf(
            "vnop_invoice_mock.report_invoice_vn", self.ids
        )

        # Create ir.attachment (raw= accepts bytes directly in Odoo 16+)
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "HoaDon_%s.pdf" % (self.name or self.id),
            "type": "binary",
            "raw": pdf_content,
            "res_model": "account.move",
            "res_id": self.id,
            "mimetype": "application/pdf",
        })

        self.write({
            "mock_einv_symbol": symbol,
            "mock_einv_issued_at": fields.Datetime.now(),
            "mock_einv_state": "issued",
            "mock_einv_pdf_attachment_id": attachment.id,
        })

    # -------------------------------------------------------------------------
    # Action: send e-invoice by email
    # -------------------------------------------------------------------------

    def action_send_einv(self):
        """Gửi HĐĐT mock qua email. Chỉ chạy khi state='issued'."""
        eligible = self.filtered(
            lambda m: m.move_type in _EINV_MOVE_TYPES
            and m.mock_einv_state == "issued"
        )
        if not eligible:
            raise UserError(
                _("Chỉ có thể gửi hóa đơn ở trạng thái 'Đã phát hành'.")
            )

        template = self.env.ref(
            "vnop_invoice_mock.mail_template_invoice_vn", raise_if_not_found=False
        )
        if not template:
            raise UserError(_("Không tìm thấy mail template hóa đơn."))

        for move in eligible:
            template.send_mail(move.id, force_send=True)
            move.mock_einv_state = "sent"
