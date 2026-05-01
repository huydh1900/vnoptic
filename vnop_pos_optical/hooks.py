# -*- coding: utf-8 -*-
"""
Post-install setup cho VNOptic POS Mắt kính.

Mục tiêu: khách hàng cài 1 module → POS chạy được ngay, kế toán theo chuẩn VN
(TT200), không phải config tay.

Quy trình hook (chạy idempotent):
  1. Đảm bảo chart of accounts VN (l10n_vn) đã load cho company.
  2. Lookup/đảm bảo các tài khoản chuẩn VN cốt lõi (1111, 1121, 131, 156,
     5111, 5113, 632, 33311, 1331).
  3. Tạo product.category 'Sản phẩm mắt kính' với property income/expense/stock
     gắn tài khoản trên.
  4. Tạo (hoặc lookup) 3 journal POS chuyên biệt + bind default_account.
  5. Bind 7 POS payment methods về journal phù hợp.
  6. Bind tax repartition đầu ra/refund của thuế GTGT 5/8/10% → 33311.
  7. Bật available_in_pos cho mọi sản phẩm sale_ok.
  8. Tạo (hoặc lookup) pos.config + bind pricelist + payment methods.
  9. Gắn product.category cho sản phẩm mẫu (gọng/tròng/phụ kiện).

Lưu ý kỹ thuật: l10n_vn chart_template loading **xoá** journals cũ. Vì vậy
journal + pos.config KHÔNG đặt trong XML data — phải tạo trong hook (chạy
SAU khi chart đã load xong).
"""
import logging

_logger = logging.getLogger(__name__)

VN_ACCOUNTS = {
    '1111': {'name': 'Tiền Việt Nam', 'type': 'asset_cash'},
    '1121': {'name': 'Tiền Việt Nam gửi ngân hàng', 'type': 'asset_cash'},
    '131':  {'name': 'Phải thu của khách hàng', 'type': 'asset_receivable'},
    '156':  {'name': 'Hàng hóa', 'type': 'asset_current'},
    '331':  {'name': 'Phải trả cho người bán', 'type': 'liability_payable'},
    '5111': {'name': 'Doanh thu bán hàng hóa', 'type': 'income'},
    '5113': {'name': 'Doanh thu cung cấp dịch vụ', 'type': 'income'},
    '632':  {'name': 'Giá vốn hàng bán', 'type': 'expense_direct_cost'},
    '6421': {'name': 'Chi phí bán hàng', 'type': 'expense'},
    '33311':{'name': 'Thuế GTGT đầu ra phải nộp', 'type': 'liability_current'},
    '1331': {'name': 'Thuế GTGT được khấu trừ', 'type': 'asset_current'},
}

# Code journal POS chuyên biệt (max 5 ký tự theo Odoo).
POS_JOURNAL_SPECS = {
    'POSMK': {'name': 'POS Mắt kính - Bán hàng', 'type': 'sale',  'account_code': '5111'},
    'POSCM': {'name': 'POS Mắt kính - Tiền mặt', 'type': 'cash', 'account_code': '1111'},
    'POSBK': {'name': 'POS Mắt kính - Ngân hàng', 'type': 'bank', 'account_code': '1121'},
}

POS_CONFIG_NAME = 'Cửa hàng Mắt kính - Quầy chính'


def _ensure_vn_chart(env, company):
    if company.chart_template:
        return
    try:
        env['account.chart.template'].try_loading('vn', company=company, install_demo=False)
        _logger.info("vnop_pos_optical: loaded l10n_vn chart for %s", company.name)
    except Exception as e:
        _logger.warning("vnop_pos_optical: cannot load vn chart: %s", e)


def _get_or_create_account(env, company, code, name, account_type):
    Account = env['account.account'].with_company(company)
    acc = Account.search([('code', '=', code), ('company_ids', 'in', company.id)], limit=1)
    if acc:
        return acc
    acc = Account.search([
        ('code', '=like', code + '%'),
        ('company_ids', 'in', company.id),
        ('account_type', '=', account_type),
    ], limit=1)
    if acc:
        return acc
    acc = Account.create({
        'code': code,
        'name': name,
        'account_type': account_type,
        'company_ids': [(4, company.id)],
    })
    _logger.info("vnop_pos_optical: created account %s - %s", code, name)
    return acc


def _setup_accounts(env, company):
    return {
        code: _get_or_create_account(env, company, code, info['name'], info['type'])
        for code, info in VN_ACCOUNTS.items()
    }


def _setup_journals(env, company, accounts):
    """Tạo (idempotent) 3 journal POS chuyên biệt với default_account VN.
    Trả dict: code → journal."""
    Journal = env['account.journal']
    journals = {}
    for code, spec in POS_JOURNAL_SPECS.items():
        j = Journal.search([
            ('code', '=', code),
            ('company_id', '=', company.id),
        ], limit=1)
        vals = {
            'name': spec['name'],
            'code': code,
            'type': spec['type'],
            'company_id': company.id,
            'show_on_dashboard': True,
        }
        acc = accounts.get(spec['account_code'])
        if acc:
            vals['default_account_id'] = acc.id
        if not j:
            j = Journal.create(vals)
            _logger.info("vnop_pos_optical: created journal %s", code)
        else:
            # Update default_account nếu đang trống
            if acc and not j.default_account_id:
                j.default_account_id = acc.id
        journals[code] = j
    return journals


def _setup_payment_methods(env, journals):
    """Bind POS payment methods về journal phù hợp."""
    cash_j = journals.get('POSCM')
    bank_j = journals.get('POSBK')

    cash_xmlids = ['vnop_pos_optical.payment_method_cash_optical']
    bank_xmlids = [
        'vnop_pos_optical.payment_method_bank_transfer',
        'vnop_pos_optical.payment_method_card_pos',
        'vnop_pos_optical.payment_method_momo',
        'vnop_pos_optical.payment_method_vnpay',
        'vnop_pos_optical.payment_method_zalopay',
        'vnop_pos_optical.payment_method_voucher',
    ]
    for xmlid in cash_xmlids:
        m = env.ref(xmlid, raise_if_not_found=False)
        if m and cash_j:
            m.journal_id = cash_j.id
    for xmlid in bank_xmlids:
        m = env.ref(xmlid, raise_if_not_found=False)
        if m and bank_j:
            m.journal_id = bank_j.id


def _setup_taxes(env, company, accounts):
    """Đảm bảo có 3 mức thuế GTGT 5/8/10% bán hàng — tạo nếu chưa có (tax
    của vnop_sale_channel có thể bị wipe khi l10n_vn load chart). Bind
    account_id của repartition line 'tax' về 33311 cho cả invoice/refund."""
    vat_out = accounts['33311']
    Tax = env['account.tax']
    for amount, label in ((5, 'Thuế GTGT 5%'), (8, 'Thuế GTGT 8%'), (10, 'Thuế GTGT 10%')):
        tax = Tax.search([
            ('amount', '=', amount),
            ('amount_type', '=', 'percent'),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not tax:
            tax = Tax.create({
                'name': label,
                'amount': amount,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'price_include_override': 'tax_excluded',
                'country_id': env.ref('base.vn').id,
                'company_id': company.id,
            })
            _logger.info("vnop_pos_optical: created tax %s", label)
        for line in tax.invoice_repartition_line_ids.filtered(
            lambda l: l.repartition_type == 'tax' and not l.account_id
        ):
            line.account_id = vat_out.id
        for line in tax.refund_repartition_line_ids.filtered(
            lambda l: l.repartition_type == 'tax' and not l.account_id
        ):
            line.account_id = vat_out.id


def _setup_product_category(env, company, accounts):
    Category = env['product.category']
    cat = Category.search([('name', '=', 'Sản phẩm mắt kính')], limit=1)
    if not cat:
        cat = Category.create({'name': 'Sản phẩm mắt kính'})
    cat_co = cat.with_company(company)
    if not cat_co.property_account_income_categ_id:
        cat_co.property_account_income_categ_id = accounts['5111'].id
    if not cat_co.property_account_expense_categ_id:
        cat_co.property_account_expense_categ_id = accounts['632'].id
    if 'property_stock_valuation_account_id' in cat._fields:
        try:
            if not cat_co.property_stock_valuation_account_id:
                cat_co.property_stock_valuation_account_id = accounts['156'].id
        except Exception:
            pass
    return cat


def _enable_pos_for_products(env):
    products = env['product.template'].search([
        ('active', '=', True),
        ('sale_ok', '=', True),
        ('type', 'in', ['consu', 'service']),
        ('available_in_pos', '=', False),
    ])
    if products:
        products.write({'available_in_pos': True})
        _logger.info("vnop_pos_optical: enabled POS on %d products", len(products))


def _bind_product_taxes(env, company):
    """Sản phẩm/dịch vụ mẫu có thể mất link tax sau khi chart wipe. Gán mặc
    định:
      - SP vật lý (consu) → thuế GTGT 8%
      - SP dịch vụ (service) → thuế GTGT 5%
    Chỉ áp khi taxes_id đang trống → idempotent, không ghi đè cấu hình thủ công."""
    Tax = env['account.tax']
    tax_8 = Tax.search([('amount', '=', 8), ('type_tax_use', '=', 'sale'),
                        ('company_id', '=', company.id)], limit=1)
    tax_5 = Tax.search([('amount', '=', 5), ('type_tax_use', '=', 'sale'),
                        ('company_id', '=', company.id)], limit=1)
    if tax_8:
        consu = env['product.template'].search([
            ('type', '=', 'consu'),
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True),
            ('taxes_id', '=', False),
        ])
        if consu:
            consu.write({'taxes_id': [(6, 0, [tax_8.id])]})
    if tax_5:
        svc = env['product.template'].search([
            ('type', '=', 'service'),
            ('sale_ok', '=', True),
            ('available_in_pos', '=', True),
            ('taxes_id', '=', False),
        ])
        if svc:
            svc.write({'taxes_id': [(6, 0, [tax_5.id])]})


def _bind_sample_products_to_category(env, category):
    pos_cat_xmlids = [
        'vnop_pos_optical.pos_cat_frame',
        'vnop_pos_optical.pos_cat_lens',
        'vnop_pos_optical.pos_cat_sunglasses',
        'vnop_pos_optical.pos_cat_contact_lens',
        'vnop_pos_optical.pos_cat_accessories',
        'vnop_pos_optical.pos_cat_service',
    ]
    pos_cats = env['pos.category']
    for xid in pos_cat_xmlids:
        c = env.ref(xid, raise_if_not_found=False)
        if c:
            pos_cats |= c
    if not pos_cats:
        return
    products = env['product.template'].search([
        ('pos_categ_ids', 'in', pos_cats.ids),
        ('categ_id.name', '!=', category.name),
    ])
    if products:
        products.write({'categ_id': category.id})


def _setup_pos_config(env, company, journals):
    """Tạo (idempotent) pos.config 'Cửa hàng Mắt kính - Quầy chính' nếu chưa
    có, gán đầy đủ pricelist + payment methods + journals + picking type."""
    PosConfig = env['pos.config']
    config = PosConfig.search([
        ('name', '=', POS_CONFIG_NAME),
        ('company_id', '=', company.id),
    ], limit=1)

    sale_j = journals.get('POSMK')
    cash_j = journals.get('POSCM')

    # Picking type cho POS — pick từ warehouse mặc định
    picking_type = env['stock.picking.type'].search([
        ('code', '=', 'outgoing'),
        ('warehouse_id.company_id', '=', company.id),
    ], limit=1)

    method_xmlids = [
        'vnop_pos_optical.payment_method_cash_optical',
        'vnop_pos_optical.payment_method_bank_transfer',
        'vnop_pos_optical.payment_method_card_pos',
        'vnop_pos_optical.payment_method_momo',
        'vnop_pos_optical.payment_method_vnpay',
        'vnop_pos_optical.payment_method_zalopay',
        'vnop_pos_optical.payment_method_voucher',
    ]
    method_ids = []
    for xmlid in method_xmlids:
        m = env.ref(xmlid, raise_if_not_found=False)
        if m:
            method_ids.append(m.id)

    retail = env.ref('vnop_sale_channel.pricelist_retail', raise_if_not_found=False)
    if not retail:
        retail = env['product.pricelist'].search([
            ('company_id', 'in', (False, company.id)),
        ], limit=1)
    # Sync currency: pricelist tạo sẵn từ data XML có thể đang USD (tuỳ thời
    # điểm install), POS yêu cầu currency khớp company → ép về VND.
    if retail and retail.currency_id != company.currency_id:
        retail.currency_id = company.currency_id.id
    wholesale = env.ref('vnop_sale_channel.pricelist_wholesale', raise_if_not_found=False)
    if wholesale and wholesale.currency_id != company.currency_id:
        wholesale.currency_id = company.currency_id.id

    vals = {
        'name': POS_CONFIG_NAME,
        'company_id': company.id,
        'limit_categories': False,
        'iface_print_auto': True,
        'iface_print_skip_screen': True,
        'iface_tax_included': 'total',
        'is_order_printer': False,
        'receipt_header': 'VNOPTIC - Cửa hàng mắt kính\nHotline: 1900-XXXX | Website: vnoptic.vn',
        'receipt_footer': ('Cảm ơn quý khách!\n'
                          'Bảo hành gọng 12 tháng - Hậu mãi trọn đời\n'
                          'Giữ hóa đơn để được hỗ trợ kiểm tra mắt định kỳ.'),
    }
    if sale_j:
        vals['journal_id'] = sale_j.id
        vals['invoice_journal_id'] = sale_j.id
    if picking_type:
        vals['picking_type_id'] = picking_type.id
    if method_ids:
        vals['payment_method_ids'] = [(6, 0, method_ids)]
    if retail:
        vals['use_pricelist'] = True
        vals['pricelist_id'] = retail.id
        vals['available_pricelist_ids'] = [(6, 0, [retail.id])]

    if not config:
        config = PosConfig.create(vals)
        _logger.info("vnop_pos_optical: created POS config '%s'", POS_CONFIG_NAME)
    elif not config.current_session_id:
        config.write(vals)


def post_init_hook(env):
    company = env.company
    _logger.info("vnop_pos_optical: starting post-init for company '%s'", company.name)

    _ensure_vn_chart(env, company)
    accounts = _setup_accounts(env, company)
    journals = _setup_journals(env, company, accounts)
    _setup_payment_methods(env, journals)
    _setup_taxes(env, company, accounts)
    category = _setup_product_category(env, company, accounts)
    _enable_pos_for_products(env)
    _bind_product_taxes(env, company)
    _bind_sample_products_to_category(env, category)
    _setup_pos_config(env, company, journals)

    _logger.info("vnop_pos_optical: post-init completed.")
