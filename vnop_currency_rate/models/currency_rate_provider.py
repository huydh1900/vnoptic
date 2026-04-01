# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

VCB_API_URL = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx?b=10"
SBV_API_URL = "https://www.sbv.gov.vn/webcenter/ShowProperty/BEA%20Repository/Publications/Exchange%20Rate/ExchangeRate"


class CurrencyRateProvider(models.Model):
    _name = "currency.rate.provider"
    _description = "Nhà cung cấp tỷ giá"

    name = fields.Char("Tên", required=True)
    active = fields.Boolean("Hoạt động", default=True)
    source = fields.Selection([
        ('vcb', 'Vietcombank'),
        ('exchangerate_api', 'ExchangeRate-API (USD base)'),
    ], string="Nguồn", required=True, default='vcb')
    api_key = fields.Char("API Key", help="Dùng cho ExchangeRate-API")
    currency_ids = fields.Many2many(
        "res.currency", string="Tiền tệ cần cập nhật",
        help="Để trống = cập nhật tất cả tiền tệ đang active"
    )
    last_sync = fields.Datetime("Lần đồng bộ cuối", readonly=True)
    log = fields.Text("Log cuối", readonly=True)

    def _fetch_vcb(self):
        """Trả về dict {currency_code: transfer_sell_rate}"""
        try:
            resp = requests.get(VCB_API_URL, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            raise UserError(_("Không thể kết nối Vietcombank: %s") % e)

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)
        rates = {}
        for item in root.findall('.//Exrate'):
            code = item.get('CurrencyCode', '').strip().upper()
            sell = item.get('Transfer', '').replace(',', '').strip()
            if code and sell:
                try:
                    rates[code] = float(sell)
                except ValueError:
                    pass
        return rates

    def _fetch_exchangerate_api(self):
        """Trả về dict {currency_code: rate_vs_VND}"""
        url = f"https://v6.exchangerate-api.com/v6/{self.api_key or 'latest'}/latest/VND"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise UserError(_("Không thể kết nối ExchangeRate-API: %s") % e)
        if data.get('result') != 'success':
            raise UserError(_("ExchangeRate-API lỗi: %s") % data.get('error-type', ''))
        # conversion_rates: {USD: 0.00004, ...} → 1 VND = x USD → 1 USD = 1/x VND
        result = {}
        for code, rate_vnd in data.get('conversion_rates', {}).items():
            if rate_vnd:
                result[code] = 1.0 / rate_vnd  # VND per 1 unit of currency
        return result

    def _get_rates(self):
        if self.source == 'vcb':
            return self._fetch_vcb()
        elif self.source == 'exchangerate_api':
            return self._fetch_exchangerate_api()
        return {}

    def action_sync(self):
        for provider in self:
            provider._do_sync()

    # Map tên currency Odoo → code VCB (khi không khớp ISO chuẩn)
    _CURRENCY_CODE_MAP = {
        'CN': 'CNY',
    }

    def _do_sync(self):
        self.ensure_one()
        Rate = self.env['res.currency.rate']
        Currency = self.env['res.currency']
        today = fields.Date.today()
        logs = []
        company = self.env.company
        base_currency = company.currency_id

        try:
            raw_rates = self._get_rates()  # {CODE: vnd_per_1_unit}
        except UserError as e:
            self.log = str(e)
            return

        # Tỷ giá VND của base currency (để quy đổi chéo)
        base_code = base_currency.name.upper()
        if base_code == 'VND':
            base_vnd = 1.0
        elif base_code in raw_rates:
            base_vnd = raw_rates[base_code]
        else:
            self.log = f"Không tìm thấy tỷ giá cho base currency {base_code}"
            return
        if not base_vnd:
            self.log = f"Tỷ giá base currency {base_code} không hợp lệ: {base_vnd}"
            return

        currencies = self.currency_ids or Currency.search([('active', '=', True)])
        target_currencies = currencies.filtered(lambda c: c.name.upper() != base_code)
        existing_rates = Rate.search([
            ('currency_id', 'in', target_currencies.ids),
            ('name', '=', today),
            ('company_id', '=', company.id),
        ])
        existing_map = {rate.currency_id.id: rate for rate in existing_rates}

        for currency in target_currencies:
            code = currency.name.upper()
            api_code = self._CURRENCY_CODE_MAP.get(code, code)
            if api_code not in raw_rates:
                logs.append(f"[SKIP] {code}: không có trong dữ liệu API")
                continue

            foreign_vnd = raw_rates[api_code]
            if not foreign_vnd:
                logs.append(f"[SKIP] {code}: tỷ giá API không hợp lệ ({foreign_vnd})")
                continue
            # Odoo rate = 1 unit foreign / base_vnd
            # Nếu base=VND: rate = 1/foreign_vnd
            odoo_rate = foreign_vnd / base_vnd if base_code != 'VND' else 1.0 / foreign_vnd

            existing = existing_map.get(currency.id)
            if existing:
                existing.rate = odoo_rate
            else:
                Rate.create({
                    'currency_id': currency.id,
                    'rate': odoo_rate,
                    'name': today,
                    'company_id': company.id,
                })
            logs.append(f"[OK] {code}: 1 {code} = {foreign_vnd:,.0f} VND | odoo_rate={odoo_rate:.8f}")

        log_content = '\n'.join(logs)
        self.write({
            'last_sync': fields.Datetime.now(),
            'log': log_content,
        })
        _logger.info("Currency rate sync done:\n%s", log_content)

    @api.model
    def _cron_sync_all(self):
        self.search([('active', '=', True)]).action_sync()
