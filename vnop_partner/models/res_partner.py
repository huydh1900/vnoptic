# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
import requests

from odoo import api, fields, models, _
from odoo.addons.base.models.res_partner import WARNING_MESSAGE, WARNING_HELP

_logger = logging.getLogger(__name__)

VIETQR_BUSINESS_URL = 'https://api.vietqr.io/v2/business'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    _sql_constraints = [
        ('ref_unique', 'unique(ref)', 'Mã khách hàng đã tồn tại, vui lòng kiểm tra lại!')
    ]

    @api.onchange('vat')
    def _onchange_vat_vietqr(self):
        if not self.vat:
            return
        vat = self.vat.strip()
        if not vat.isdigit() or len(vat) < 10:
            return
        try:
            response = requests.get(
                '%s/%s' % (VIETQR_BUSINESS_URL, vat),
                timeout=3,
            )
            response.raise_for_status()
            result = response.json()
        except Exception:
            _logger.warning("VietQR API lookup failed for VAT: %s", vat)
            return {'warning': {
                'title': _("Không tìm thấy MST"),
                'message': _("Mã số thuế %s không tồn tại trên hệ thống Tổng cục Thuế.") % vat,
            }}
        if result.get('code') != '00' or not result.get('data'):
            return {'warning': {
                'title': _("Không tìm thấy MST"),
                'message': _("Mã số thuế %s không tồn tại trên hệ thống Tổng cục Thuế.") % vat,
            }}
        data = result['data']
        vietnam = self.env.ref('base.vn', raise_if_not_found=False)
        if vietnam:
            self.country_id = vietnam
        if data.get('name') and not self.name:
            self.name = data['name']
        if data.get('address'):
            self._fill_address_from_vietqr(data['address'])

    def _fill_address_from_vietqr(self, address):
        """Parse VietQR address and fill street, city, state_id."""
        vietnam = self.country_id if self.country_id.code == 'VN' else self.env.ref('base.vn', raise_if_not_found=False)
        if not vietnam:
            self.street = address
            return
        parts = [p.strip() for p in address.split(',')]
        if len(parts) < 2:
            self.street = address
            return
        # Phần cuối thường là tỉnh/TP
        province_part = parts[-1]
        state = self._match_vn_state(province_part, vietnam)
        if state:
            self.state_id = state
            remaining = parts[:-1]
        else:
            remaining = parts[:]
        # Phần gần cuối có thể là quận/huyện/thành phố (city)
        if len(remaining) >= 2:
            self.city = remaining[-1]
            self.street = ', '.join(remaining[:-1])
        elif remaining:
            self.street = remaining[0]

    def _match_vn_state(self, text, country):
        """Match text against VN state names with normalization."""
        text_normalized = self._normalize_province_name(text)
        states = self.env['res.country.state'].search([
            ('country_id', '=', country.id),
        ])
        for state in states:
            if self._normalize_province_name(state.name) == text_normalized:
                return state
        # Fallback: tìm state chứa text hoặc text chứa state name
        for state in states:
            state_norm = self._normalize_province_name(state.name)
            if state_norm in text_normalized or text_normalized in state_norm:
                return state
        return False

    @staticmethod
    def _normalize_province_name(name):
        """Chuẩn hóa tên tỉnh: bỏ prefix TP/Tỉnh/Thành phố, lowercase."""
        name = name.strip()
        name = re.sub(
            r'^(TP\.?\s*|Tỉnh\s+|Thành\s+phố\s+)',
            '',
            name,
            flags=re.IGNORECASE,
        )
        return name.strip().lower()
