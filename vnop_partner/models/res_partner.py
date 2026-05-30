# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
import requests

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

VIETQR_BUSINESS_URL = 'https://api.vietqr.io/v2/business'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    _sql_constraints = [
        ('ref_unique', 'unique(ref)', 'Mã khách hàng đã tồn tại, vui lòng kiểm tra lại!')
    ]

    ward_id = fields.Many2one(
        'vnop.ward', string='Phường/Xã',
        domain="[('state_id', '=', state_id)]",
        ondelete='restrict',
    )

    @api.onchange('ward_id')
    def _onchange_ward_id(self):
        if self.ward_id:
            self.city = self.ward_id.name
            if self.ward_id.state_id and self.state_id != self.ward_id.state_id:
                self.state_id = self.ward_id.state_id

    @api.onchange('state_id')
    def _onchange_state_id_reset_ward(self):
        if self.ward_id and self.ward_id.state_id != self.state_id:
            self.ward_id = False

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
        except (requests.RequestException, ValueError, KeyError):
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
        """Parse VietQR address theo cấu trúc 2 cấp sau 2025-07-01:
        street, ..., phường/xã, tỉnh/TP. Match từ phải sang trái.
        """
        vietnam = self.country_id if self.country_id.code == 'VN' else self.env.ref('base.vn', raise_if_not_found=False)
        if not vietnam:
            self.street = address
            return
        parts = [p.strip() for p in address.split(',') if p.strip()]
        if len(parts) < 2:
            self.street = address
            return

        remaining = parts[:]

        # 1) Tỉnh/TP ở phần cuối
        state = self._match_vn_state(remaining[-1], vietnam)
        if state:
            self.state_id = state
            remaining.pop()

        # 2) Phường/Xã: thử các phần còn lại từ phải sang, ưu tiên state_id
        ward = False
        for idx in range(len(remaining) - 1, -1, -1):
            ward = self._match_vn_ward(remaining[idx], state)
            if ward:
                # Nếu ward match được state khác, override state cũ
                if state and ward.state_id != state:
                    continue
                self.ward_id = ward
                if not state and ward.state_id:
                    self.state_id = ward.state_id
                remaining.pop(idx)
                break

        if remaining:
            self.street = ', '.join(remaining)

    def _match_vn_ward(self, text, state):
        """Match text với vnop.ward, optionally filter theo state."""
        text_norm = self._normalize_ward_name(text)
        if not text_norm:
            return False
        domain = []
        if state:
            domain.append(('state_id', '=', state.id))
        wards = self.env['vnop.ward'].search(domain)
        for w in wards:
            if self._normalize_ward_name(w.name) == text_norm:
                return w
        return False

    @staticmethod
    def _normalize_ward_name(name):
        """Chuẩn hóa tên phường/xã: bỏ prefix Phường/Xã/Thị trấn, lowercase."""
        name = (name or '').strip()
        name = re.sub(
            r'^(phường\s+|xã\s+|thị\s+trấn\s+|p\.\s*|x\.\s*|tt\.\s*)',
            '',
            name,
            flags=re.IGNORECASE,
        )
        return name.strip().lower()

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
