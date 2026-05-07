# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager


class B2BPortal(CustomerPortal):
    """Portal B2B đại lý: catalog, cart, đặt đơn, công nợ, RMA."""

    _B2B_PAGE_SIZE = 20

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _b2b_partner(self):
        """Trả về commercial_partner_id của user hiện tại.

        Raise NotFound nếu:
        - Không phải wholesale partner
        - Hoặc is_b2b_portal_active = False
        - Hoặc company mismatch
        """
        partner = request.env.user.partner_id.commercial_partner_id
        if (
            not partner
            or partner.channel_type != 'wholesale'
            or not partner.is_b2b_portal_active
        ):
            raise MissingError("Bạn không có quyền truy cập cổng B2B đại lý.")

        # Multi-company check: partner phải thuộc company hiện tại
        if partner.company_id and partner.company_id.id != request.env.company.id:
            raise MissingError("Công ty không khớp.")

        return partner

    def _b2b_partner_safe(self):
        """Trả về partner hoặc None (không raise)."""
        try:
            return self._b2b_partner()
        except (MissingError, AccessError):
            return None

    def _b2b_pricelist(self, partner):
        """Trả pricelist từ partner hoặc default của company."""
        pricelist = partner.property_product_pricelist
        if pricelist:
            return pricelist
        # Fallback: pricelist mặc định của company
        return request.env['product.pricelist'].sudo().search([
            ('company_id', 'in', (False, request.env.company.id)),
        ], limit=1)

    def _b2b_cart_get(self):
        """Đọc cart từ session. Format: {str(product_id): qty}."""
        return dict(request.session.get('b2b_cart', {}))

    def _b2b_cart_set(self, cart):
        """Ghi cart vào session sau khi validate product_id tồn tại + sale_ok=True."""
        valid_cart = {}
        if cart:
            product_ids = [int(pid) for pid in cart.keys()]
            valid_products = request.env['product.product'].sudo().search([
                ('id', 'in', product_ids),
                ('sale_ok', '=', True),
                ('active', '=', True),
            ])
            valid_ids = {p.id for p in valid_products}
            for pid_str, qty in cart.items():
                pid = int(pid_str)
                if pid in valid_ids and qty > 0:
                    valid_cart[str(pid)] = qty
        request.session['b2b_cart'] = valid_cart

    def _b2b_get_cart_products(self, cart, partner, pricelist):
        """Trả list dict với product detail + price cho hiển thị cart.

        Batch load để tránh N+1.
        """
        if not cart:
            return []
        product_ids = [int(pid) for pid in cart.keys()]
        today = fields.Date.today()
        products = request.env['product.product'].sudo().browse(product_ids).filtered(
            lambda p: p.active and p.sale_ok
        )
        result = []
        for product in products:
            qty = cart.get(str(product.id), 0)
            if qty <= 0:
                continue
            price = pricelist._get_product_price(
                product, qty,
                uom=product.uom_id,
                date=today,
            )
            result.append({
                'product': product,
                'qty': qty,
                'price_unit': price,
                'subtotal': price * qty,
            })
        return result

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = self._b2b_partner_safe()
        if not partner:
            return values

        cart = self._b2b_cart_get()
        cart_count = sum(int(q) for q in cart.values())

        if 'b2b_order_count' in counters:
            values['b2b_order_count'] = request.env['sale.order'].sudo().search_count([
                ('partner_id.commercial_partner_id', '=', partner.id),
                ('state', '!=', 'cancel'),
            ])
        if 'b2b_cart_count' in counters:
            values['b2b_cart_count'] = cart_count
        if 'b2b_invoice_count' in counters:
            values['b2b_invoice_count'] = request.env['account.move'].sudo().search_count([
                ('partner_id.commercial_partner_id', '=', partner.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('payment_state', 'not in', ('paid', 'in_payment')),
                ('state', '=', 'posted'),
            ])

        values['is_user_b2b'] = partner
        values['b2b_cart_count'] = cart_count
        return values

    # -------------------------------------------------------------------------
    # Routes — Catalog
    # -------------------------------------------------------------------------

    @http.route('/my/catalog', type='http', auth='user', website=True)
    def b2b_catalog(self, page=1, category_id=None, search='', **kw):
        partner = self._b2b_partner()
        pricelist = self._b2b_pricelist(partner)
        today = fields.Date.today()

        domain = [('sale_ok', '=', True), ('active', '=', True)]
        if category_id:
            try:
                category_id = int(category_id)
                domain.append(('categ_id', 'child_of', category_id))
            except (ValueError, TypeError):
                category_id = None
        if search:
            domain += ['|',
                ('name', 'ilike', search),
                ('default_code', 'ilike', search),
            ]

        Product = request.env['product.product'].sudo()
        total = Product.search_count(domain)
        pg = pager(
            url='/my/catalog',
            total=total,
            page=int(page),
            step=self._B2B_PAGE_SIZE,
            url_args={'category_id': category_id or '', 'search': search},
        )
        products_raw = Product.search(domain, offset=pg['offset'], limit=self._B2B_PAGE_SIZE)

        # Batch price fetch
        product_lines = []
        for product in products_raw:
            price = pricelist._get_product_price(
                product, 1,
                uom=product.uom_id,
                date=today,
            )
            product_lines.append({'product': product, 'price': price})

        # Category filter options
        categories = request.env['product.category'].sudo().search([])

        values = self._prepare_portal_layout_values()
        values.update({
            'is_user_b2b': partner,
            'product_lines': product_lines,
            'pager': pg,
            'search': search,
            'category_id': category_id,
            'categories': categories,
            'currency': pricelist.currency_id,
            'page_name': 'b2b_catalog',
        })
        return request.render('vnop_b2b_portal.portal_catalog', values)

    # -------------------------------------------------------------------------
    # Routes — Cart
    # -------------------------------------------------------------------------

    @http.route('/my/cart/add', type='http', auth='user', website=True, methods=['POST'])
    def b2b_cart_add(self, product_id, qty=1, **kw):
        self._b2b_partner()
        cart = self._b2b_cart_get()
        try:
            product_id = int(product_id)
            qty = max(1, int(qty))
        except (ValueError, TypeError):
            return request.redirect('/my/catalog')

        key = str(product_id)
        cart[key] = cart.get(key, 0) + qty
        self._b2b_cart_set(cart)
        return request.redirect('/my/catalog')

    @http.route('/my/cart', type='http', auth='user', website=True)
    def b2b_cart(self, **kw):
        partner = self._b2b_partner()
        pricelist = self._b2b_pricelist(partner)
        cart = self._b2b_cart_get()
        cart_lines = self._b2b_get_cart_products(cart, partner, pricelist)
        total = sum(line['subtotal'] for line in cart_lines)

        values = self._prepare_portal_layout_values()
        values.update({
            'is_user_b2b': partner,
            'cart_lines': cart_lines,
            'cart_total': total,
            'currency': pricelist.currency_id,
            'page_name': 'b2b_cart',
        })
        return request.render('vnop_b2b_portal.portal_cart', values)

    @http.route('/my/cart/update', type='http', auth='user', website=True, methods=['POST'])
    def b2b_cart_update(self, **kw):
        self._b2b_partner()
        cart = self._b2b_cart_get()
        # Hỗ trợ cập nhật nhiều dòng cùng lúc: qty_<pid>=<qty>
        for key, val in kw.items():
            if key.startswith('qty_'):
                try:
                    pid = str(int(key[4:]))
                    qty = int(val)
                    if qty <= 0:
                        cart.pop(pid, None)
                    else:
                        cart[pid] = qty
                except (ValueError, TypeError):
                    continue
        self._b2b_cart_set(cart)
        return request.redirect('/my/cart')

    @http.route('/my/cart/checkout', type='http', auth='user', website=True, methods=['POST'])
    def b2b_cart_checkout(self, **kw):
        partner = self._b2b_partner()
        pricelist = self._b2b_pricelist(partner)
        cart = self._b2b_cart_get()

        if not cart:
            return request.redirect('/my/cart')

        today = fields.Date.today()
        product_ids = [int(pid) for pid in cart.keys()]
        products = request.env['product.product'].sudo().search([
            ('id', 'in', product_ids),
            ('sale_ok', '=', True),
            ('active', '=', True),
        ])
        valid_ids = {p.id: p for p in products}

        skipped_products = []
        order_lines = []
        for pid_str, qty in cart.items():
            pid = int(pid_str)
            product = valid_ids.get(pid)
            if not product:
                skipped_products.append(pid_str)
                continue
            price = pricelist._get_product_price(
                product, qty,
                uom=product.uom_id,
                date=today,
            )
            order_lines.append((0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'price_unit': price,
            }))

        if not order_lines:
            return request.redirect('/my/cart')

        order_vals = {
            'partner_id': partner.id,
            'pricelist_id': pricelist.id,
            'order_line': order_lines,
        }
        # channel_type: chỉ set nếu field tồn tại (từ vnop_sale_channel)
        if 'channel_type' in request.env['sale.order']._fields:
            order_vals['channel_type'] = 'wholesale'

        SaleOrder = request.env['sale.order'].sudo()
        order = SaleOrder.create(order_vals)
        order._compute_amounts()

        # Xóa cart
        self._b2b_cart_set({})

        # Cảnh báo nếu có sản phẩm bị bỏ qua
        if skipped_products:
            request.session['b2b_checkout_warning'] = (
                'Một số sản phẩm đã bị xóa hoặc không còn khả dụng và đã bị bỏ qua.'
            )

        return request.redirect(order.get_portal_url())

    # -------------------------------------------------------------------------
    # Routes — Financial
    # -------------------------------------------------------------------------

    @http.route('/my/financial', type='http', auth='user', website=True)
    def b2b_financial(self, **kw):
        partner = self._b2b_partner()
        today = fields.Date.today()

        AccountMove = request.env['account.move'].sudo()
        unpaid_invoices = AccountMove.search([
            ('partner_id.commercial_partner_id', '=', partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ('paid', 'in_payment')),
        ], order='invoice_date_due asc')

        # Tổng dư nợ
        total_overdue = sum(inv.amount_residual for inv in unpaid_invoices)

        # Paid this month: tháng hiện tại (1st → today)
        month_start = today.replace(day=1)
        paid_invoices = AccountMove.search([
            ('partner_id.commercial_partner_id', '=', partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('paid', 'in_payment')),
            ('invoice_date', '>=', month_start),
            ('invoice_date', '<=', today),
        ])
        paid_this_month = sum(inv.amount_total for inv in paid_invoices)

        # Aging buckets
        aging_buckets = {'0-30': 0.0, '31-60': 0.0, '61-90': 0.0, 'over-90': 0.0}
        for inv in unpaid_invoices:
            days = (today - inv.invoice_date_due).days if inv.invoice_date_due else 0
            if days <= 30:
                aging_buckets['0-30'] += inv.amount_residual
            elif days <= 60:
                aging_buckets['31-60'] += inv.amount_residual
            elif days <= 90:
                aging_buckets['61-90'] += inv.amount_residual
            else:
                aging_buckets['over-90'] += inv.amount_residual

        currency = request.env.company.currency_id
        values = self._prepare_portal_layout_values()
        values.update({
            'is_user_b2b': partner,
            'unpaid_invoices': unpaid_invoices,
            'total_overdue': total_overdue,
            'paid_this_month': paid_this_month,
            'aging_buckets': aging_buckets,
            'currency': currency,
            'today': today,
            'page_name': 'b2b_financial',
        })
        return request.render('vnop_b2b_portal.portal_financial', values)

    # -------------------------------------------------------------------------
    # Routes — Returns (RMA) — soft dependency vnop_sale_workflow
    # -------------------------------------------------------------------------

    @http.route('/my/returns', type='http', auth='user', website=True)
    def b2b_returns(self, **kw):
        partner = self._b2b_partner()
        values = self._prepare_portal_layout_values()
        values['is_user_b2b'] = partner
        values['page_name'] = 'b2b_returns'

        if 'vnop.rma' not in request.env:
            values['rma_unavailable'] = True
            values['rma_list'] = []
            return request.render('vnop_b2b_portal.portal_returns_list', values)

        rma_list = request.env['vnop.rma'].sudo().search([
            ('partner_id.commercial_partner_id', '=', partner.id),
            ('state', 'in', ('submitted', 'approved', 'rejected')),
        ], order='id desc')
        values['rma_list'] = rma_list
        values['rma_unavailable'] = False
        return request.render('vnop_b2b_portal.portal_returns_list', values)

    @http.route('/my/returns/new', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def b2b_returns_new(self, **kw):
        partner = self._b2b_partner()
        values = self._prepare_portal_layout_values()
        values['is_user_b2b'] = partner
        values['page_name'] = 'b2b_returns_new'

        if 'vnop.rma' not in request.env:
            return request.redirect('/my/returns')

        SaleOrder = request.env['sale.order'].sudo()
        orders = SaleOrder.search([
            ('partner_id.commercial_partner_id', '=', partner.id),
            ('state', 'in', ('sale', 'done')),
        ], order='id desc')

        if request.httprequest.method == 'POST':
            return self._b2b_returns_submit(partner, orders, **kw)

        values.update({
            'orders': orders,
            'error': {},
            'kw': None,
            'reason_codes': [
                ('defect', 'Hàng lỗi'),
                ('wrong_item', 'Sai mặt hàng'),
                ('customer_change', 'Khách đổi ý'),
                ('quality_issue', 'Lỗi chất lượng'),
                ('other', 'Khác'),
            ],
            'resolution_types': [
                ('refund', 'Hoàn tiền'),
                ('replace', 'Đổi hàng'),
                ('credit_note', 'Giảm trừ công nợ'),
            ],
        })
        return request.render('vnop_b2b_portal.portal_returns_form', values)

    def _b2b_returns_submit(self, partner, orders, **kw):
        """Xử lý POST tạo vnop.rma mới."""
        error = {}
        order_id = kw.get('sale_order_id')
        reason_code = kw.get('reason_code')
        resolution_type = kw.get('resolution_type', 'refund')
        reason_note = kw.get('reason_note', '')

        if not order_id:
            error['sale_order_id'] = True
        if not reason_code:
            error['reason_code'] = True

        order = None
        if order_id and not error:
            try:
                order = request.env['sale.order'].sudo().browse(int(order_id))
                # Kiểm tra order thuộc đúng partner
                if order.partner_id.commercial_partner_id.id != partner.id:
                    error['sale_order_id'] = True
                    order = None
            except (ValueError, TypeError, MissingError):
                error['sale_order_id'] = True

        if error:
            values = self._prepare_portal_layout_values()
            values.update({
                'is_user_b2b': partner,
                'page_name': 'b2b_returns_new',
                'orders': orders,
                'error': error,
                'kw': kw,
                'reason_codes': [
                    ('defect', 'Hàng lỗi'),
                    ('wrong_item', 'Sai mặt hàng'),
                    ('customer_change', 'Khách đổi ý'),
                    ('quality_issue', 'Lỗi chất lượng'),
                    ('other', 'Khác'),
                ],
                'resolution_types': [
                    ('refund', 'Hoàn tiền'),
                    ('replace', 'Đổi hàng'),
                    ('credit_note', 'Giảm trừ công nợ'),
                ],
            })
            return request.render('vnop_b2b_portal.portal_returns_form', values)

        rma = request.env['vnop.rma'].sudo().create({
            'sale_order_id': order.id,
            'reason_code': reason_code,
            'resolution_type': resolution_type,
            'reason_note': reason_note,
            'state': 'submitted',
            'company_id': request.env.company.id,
        })
        # Sinh mã sequence
        sequence = request.env['ir.sequence'].sudo().next_by_code('vnop.rma')
        if sequence:
            rma.write({'name': sequence})

        return request.redirect('/my/returns')
