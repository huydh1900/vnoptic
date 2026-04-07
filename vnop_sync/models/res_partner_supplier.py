import re
import unicodedata
from odoo import api, fields, models

# -*- coding: utf-8 -*-




class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_supplier_fax = fields.Char(string='Fax')
    x_supplier_contact_name = fields.Char(string='Người liên hệ')


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    x_bank_address = fields.Char(string='Địa chỉ ngân hàng', related='bank_id.street', readonly=False, store=True)

    # Đã bỏ x_bank_country, dùng trực tiếp bank_id.country (Odoo base)

    def _normalize_bank_token(self, value):
        if value in (None, False):
            return ''
        raw = str(value).strip().lower()
        if not raw:
            return ''
        normalized = unicodedata.normalize('NFKD', raw)
        normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r'[^a-z0-9]+', '', normalized)
        return normalized

    def _is_invalid_bank_token(self, value):
        normalized = self._normalize_bank_token(value)
        if not normalized:
            return True
        invalid_tokens = {'khong', 'none', 'null', 'na'}
        if normalized in invalid_tokens:
            return True
        for token in invalid_tokens:
            if normalized.startswith(token) and normalized[len(token):].isdigit():
                return True
        return False

    def _is_invalid_bank_block(self, bank_name, account_no):
        return self._is_invalid_bank_token(bank_name) or self._is_invalid_bank_token(account_no)

    @api.model
    def migrate_invalid_bank_fields(self):
        """
        Tìm và cleanup block ngân hàng khi advisingBank/accountNo không hợp lệ.
        - Nếu bank name hoặc acc_number là placeholder => archive res.partner.bank.
        - Xóa placeholder ở bic/street để không hiện dữ liệu bẩn.
        """
        partner_banks = self.with_context(active_test=False).search([])
        invalid_bank_ids = set()

        for partner_bank in partner_banks:
            bank = partner_bank.bank_id
            bank_name = bank.name if bank else False
            acc_number = partner_bank.acc_number
            if self._is_invalid_bank_block(bank_name, acc_number):
                partner_bank.write({'active': False})
                if bank and self._is_invalid_bank_token(bank.name):
                    invalid_bank_ids.add(bank.id)
            if bank:
                bank_write_vals = {}
                if self._is_invalid_bank_token(bank.bic):
                    bank_write_vals['bic'] = False
                if self._is_invalid_bank_token(bank.street):
                    bank_write_vals['street'] = False
                if bank_write_vals:
                    bank.write(bank_write_vals)

        if invalid_bank_ids:
            banks = self.env['res.bank'].browse(list(invalid_bank_ids)).exists()
            for bank in banks:
                if not self.with_context(active_test=False).search_count([('bank_id', '=', bank.id)]):
                    bank.unlink()
