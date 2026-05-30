# -*- coding: utf-8 -*-
import json

from odoo import fields, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager


class B2BPortal(CustomerPortal):
    """Portal B2B đại lý: đơn yêu cầu đặt hàng (CRUD), công nợ."""

    _B2B_ORDER_PAGE_SIZE = 20

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _b2b_partner(self):
        """Trả về commercial_partner_id của user hiện tại.

        Raise nếu không phải portal user hoặc company mismatch.
        """
        user = request.env.user
        if not user.share:
            raise MissingError("Bạn không có quyền truy cập cổng B2B đại lý.")
        partner = user.partner_id.commercial_partner_id
        if not partner:
            raise MissingError("Bạn không có quyền truy cập cổng B2B đại lý.")
        if partner.company_id and partner.company_id.id != request.env.company.id:
            raise MissingError("Công ty không khớp.")
        return partner

    def _b2b_partner_safe(self):
        try:
            return self._b2b_partner()
        except (MissingError, AccessError):
            return None

    def _b2b_pricelist(self, partner):
        pricelist = partner.property_product_pricelist
        if pricelist:
            return pricelist
        return request.env['product.pricelist'].sudo().search([
            ('company_id', 'in', (False, request.env.company.id)),
        ], limit=1)

    def _b2b_request_domain(self, partner):
        """Domain chuẩn cho đơn yêu cầu B2B của dealer (loại trừ cancelled)."""
        return [
            ('commercial_partner_id', '=', partner.id),
            ('state', '!=', 'cancelled'),
        ]

    def _b2b_get_request(self, request_id, partner):
        """Browse + verify ownership."""
        rec = request.env['vnop.order.request'].sudo().browse(int(request_id)).exists()
        if not rec or rec.commercial_partner_id.id != partner.id:
            raise MissingError("Đơn yêu cầu không tồn tại.")
        return rec

    def _b2b_request_lines_view(self, order_request):
        """Map request lines → list dict cho template (kèm brand/model/color)."""
        result = []
        for ln in order_request.line_ids:
            tmpl = ln.product_id.product_tmpl_id
            result.append({
                'line': ln,
                'product': ln.product_id,
                'brand': tmpl.brand_id.name or '' if 'brand_id' in tmpl._fields else '',
                'model': (tmpl.opt_model if 'opt_model' in tmpl._fields else '')
                         or ln.product_id.default_code or '',
                'color': tmpl.opt_color if 'opt_color' in tmpl._fields else '',
            })
        return result

    def _b2b_dealer_address(self, partner):
        return ', '.join(
            ln.strip() for ln in partner.sudo()._display_address(without_company=True).split('\n')
            if ln.strip()
        )

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = self._b2b_partner_safe()
        if not partner:
            return values

        is_initial_render = not counters

        if is_initial_render or 'b2b_order_count' in counters:
            values['b2b_order_count'] = request.env['vnop.order.request'].sudo().search_count(
                self._b2b_request_domain(partner)
            )
        if is_initial_render or 'b2b_invoice_count' in counters:
            values['b2b_invoice_count'] = request.env['account.move'].sudo().search_count([
                ('partner_id.commercial_partner_id', '=', partner.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('payment_state', 'not in', ('paid', 'in_payment')),
                ('state', '=', 'posted'),
            ])

        if is_initial_render:
            values['is_user_b2b'] = partner
        return values

    # -------------------------------------------------------------------------
    # Routes — Đơn yêu cầu đặt hàng (list + detail + CRUD)
    # -------------------------------------------------------------------------

    @http.route('/my/b2b/orders', type='http', auth='user', website=True)
    def b2b_orders(self, page=1, search='', **kw):
        partner = self._b2b_partner()
        domain = self._b2b_request_domain(partner)
        if search:
            domain += [('name', 'ilike', search)]

        OrderRequest = request.env['vnop.order.request'].sudo()
        total = OrderRequest.search_count(domain)
        pg = pager(
            url='/my/b2b/orders',
            total=total,
            page=int(page),
            step=self._B2B_ORDER_PAGE_SIZE,
            url_args={'search': search},
        )
        orders = OrderRequest.search(
            domain, offset=pg['offset'], limit=self._B2B_ORDER_PAGE_SIZE,
            order='create_date desc',
        )

        values = self._prepare_portal_layout_values()
        values.update({
            'is_user_b2b': partner,
            'orders': orders,
            'pager': pg,
            'search': search,
            'page_name': 'b2b_orders',
        })
        return request.render('vnop_b2b_portal.portal_orders_list', values)

    @http.route('/my/b2b/orders/new', type='http', auth='user', website=True, methods=['POST'])
    def b2b_order_new(self, **kw):
        partner = self._b2b_partner()
        pricelist = self._b2b_pricelist(partner)
        order_request = request.env['vnop.order.request'].sudo().create({
            'partner_id': partner.id,
            'pricelist_id': pricelist.id if pricelist else False,
        })
        return request.redirect(f'/my/b2b/orders/{order_request.id}')

    @http.route('/my/b2b/orders/<int:order_id>', type='http', auth='user', website=True)
    def b2b_order_detail(self, order_id, **kw):
        partner = self._b2b_partner()
        order_request = self._b2b_get_request(order_id, partner)
        pricelist = order_request.pricelist_id or self._b2b_pricelist(partner)

        values = self._prepare_portal_layout_values()
        values.update({
            'is_user_b2b': partner,
            'order': order_request,
            'order_lines_view': self._b2b_request_lines_view(order_request),
            'can_edit': order_request.state == 'draft',
            'currency': pricelist.currency_id if pricelist else order_request.currency_id,
            'company': request.env.company.sudo(),
            'dealer': partner.sudo(),
            'dealer_address': self._b2b_dealer_address(partner),
            'page_name': 'b2b_orders',
        })
        return request.render('vnop_b2b_portal.portal_order_form', values)

    def _b2b_assert_editable(self, order_request):
        if order_request.state != 'draft':
            raise UserError("Đơn đã gửi, không thể chỉnh sửa.")

    @http.route('/my/b2b/orders/<int:order_id>/line/add',
                type='http', auth='user', website=True, methods=['POST'])
    def b2b_order_line_add(self, order_id, product_id, qty=1, **kw):
        partner = self._b2b_partner()
        order_request = self._b2b_get_request(order_id, partner)
        self._b2b_assert_editable(order_request)
        try:
            product_id = int(product_id)
            qty = max(1, int(qty))
        except (ValueError, TypeError):
            return request.redirect(f'/my/b2b/orders/{order_request.id}')

        product = request.env['product.product'].sudo().browse(product_id).exists()
        if not product or not product.sale_ok or not product.active:
            return request.redirect(f'/my/b2b/orders/{order_request.id}')

        # Nếu đã có line cùng product → cộng qty thay vì tạo mới
        existing = order_request.line_ids.filtered(lambda ln: ln.product_id.id == product.id)
        if existing:
            existing[0].product_uom_qty = existing[0].product_uom_qty + qty
        else:
            request.env['vnop.order.request.line'].sudo().create({
                'request_id': order_request.id,
                'product_id': product.id,
                'name': product.display_name,
                'product_uom': product.uom_id.id,
                'product_uom_qty': qty,
                'price_unit': order_request._get_price_unit(product, qty),
            })
        return request.redirect(f'/my/b2b/orders/{order_request.id}')

    @http.route('/my/b2b/orders/<int:order_id>/line/update',
                type='http', auth='user', website=True, methods=['POST'])
    def b2b_order_line_update(self, order_id, **kw):
        partner = self._b2b_partner()
        order_request = self._b2b_get_request(order_id, partner)
        self._b2b_assert_editable(order_request)

        for key, val in kw.items():
            if not key.startswith('qty_'):
                continue
            try:
                line_id = int(key[4:])
                qty = int(val)
            except (ValueError, TypeError):
                continue
            line = order_request.line_ids.filtered(lambda ln: ln.id == line_id)
            if not line:
                continue
            if qty <= 0:
                line.unlink()
            else:
                line.product_uom_qty = qty
        return request.redirect(f'/my/b2b/orders/{order_request.id}')

    @http.route('/my/b2b/orders/<int:order_id>/line/<int:line_id>/remove',
                type='http', auth='user', website=True, methods=['POST'])
    def b2b_order_line_remove(self, order_id, line_id, **kw):
        partner = self._b2b_partner()
        order_request = self._b2b_get_request(order_id, partner)
        self._b2b_assert_editable(order_request)
        line = order_request.line_ids.filtered(lambda ln: ln.id == line_id)
        if line:
            line.unlink()
        return request.redirect(f'/my/b2b/orders/{order_request.id}')

    @http.route('/my/b2b/orders/<int:order_id>/submit',
                type='http', auth='user', website=True, methods=['POST'])
    def b2b_order_submit(self, order_id, **kw):
        partner = self._b2b_partner()
        order_request = self._b2b_get_request(order_id, partner)
        self._b2b_assert_editable(order_request)
        if not order_request.line_ids:
            return request.redirect(f'/my/b2b/orders/{order_request.id}')
        order_request.action_submit()
        return request.redirect(f'/my/b2b/orders/{order_request.id}')

    @http.route('/my/b2b/orders/<int:order_id>/cancel',
                type='http', auth='user', website=True, methods=['POST'])
    def b2b_order_cancel(self, order_id, **kw):
        """Hủy đơn nháp (chưa gửi)."""
        partner = self._b2b_partner()
        order_request = self._b2b_get_request(order_id, partner)
        self._b2b_assert_editable(order_request)
        order_request.action_cancel()
        return request.redirect('/my/b2b/orders')

    # -------------------------------------------------------------------------
    # Routes — Brand/Model/Color cascade (JSON)
    # -------------------------------------------------------------------------

    def _b2b_json(self, payload):
        return request.make_response(
            json.dumps(payload),
            headers=[('Content-Type', 'application/json')],
        )

    @http.route('/my/b2b/products/brands', type='http', auth='user', website=True)
    def b2b_products_brands(self, **kw):
        self._b2b_partner()
        templates = request.env['product.template'].sudo().search([
            ('sale_ok', '=', True),
            ('active', '=', True),
            ('brand_id', '!=', False),
        ])
        brands = templates.brand_id.sorted('name')
        return self._b2b_json({'results': [{'id': b.id, 'name': b.name} for b in brands]})

    @http.route('/my/b2b/products/models', type='http', auth='user', website=True)
    def b2b_products_models(self, brand_id=None, **kw):
        self._b2b_partner()
        try:
            brand_id = int(brand_id)
        except (TypeError, ValueError):
            return self._b2b_json({'results': []})
        templates = request.env['product.template'].sudo().search([
            ('sale_ok', '=', True),
            ('active', '=', True),
            ('brand_id', '=', brand_id),
            ('opt_model', '!=', False),
        ])
        models = sorted({t.opt_model for t in templates if t.opt_model})
        return self._b2b_json({'results': [{'model': m} for m in models]})

    @http.route('/my/b2b/products/colors', type='http', auth='user', website=True)
    def b2b_products_colors(self, brand_id=None, opt_model=None, **kw):
        self._b2b_partner()
        try:
            brand_id = int(brand_id)
        except (TypeError, ValueError):
            return self._b2b_json({'results': []})
        opt_model = (opt_model or '').strip()
        if not opt_model:
            return self._b2b_json({'results': []})
        templates = request.env['product.template'].sudo().search([
            ('sale_ok', '=', True),
            ('active', '=', True),
            ('brand_id', '=', brand_id),
            ('opt_model', '=', opt_model),
            ('opt_color', '!=', False),
        ])
        # Group by color (lấy variant chính của template đầu tiên match)
        seen = {}
        for t in templates:
            c = (t.opt_color or '').strip()
            if c and c not in seen and t.product_variant_id:
                seen[c] = t.product_variant_id.id
        results = [{'color': c, 'product_id': pid} for c, pid in sorted(seen.items())]
        return self._b2b_json({'results': results})

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

        total_overdue = sum(inv.amount_residual for inv in unpaid_invoices)

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
