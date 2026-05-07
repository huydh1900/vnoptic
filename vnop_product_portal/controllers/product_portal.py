# -*- coding: utf-8 -*-
import base64

from odoo import http
from odoo.http import request

PLACEHOLDER = 'Đang cập nhật'


class ProductPortalController(http.Controller):

    def _resolve_product(self, product_id):
        """Tìm product.template theo legacy_product_id (QR cũ in từ hệ thống Java)
        trước, sau đó fallback về Odoo internal id (QR sinh sau khi chuyển sang Odoo).
        """
        Product = request.env['product.template'].sudo()
        product = Product.search(
            [('legacy_product_id', '=', product_id), ('active', '=', True)],
            limit=1,
        )
        if not product:
            product = Product.search(
                [('id', '=', product_id), ('active', '=', True)],
                limit=1,
            )
        return product

    def _render_product(self, product_id):
        product = self._resolve_product(product_id)
        if not product:
            return request.not_found()

        currency = product.currency_id

        def _or_placeholder(val):
            return val if val not in (False, None, '', 0, 0.0) else PLACEHOLDER

        sph = product.x_sph or PLACEHOLDER
        cyl = product.x_cyl or PLACEHOLDER
        add = ('%.2f' % product.x_add) if product.x_add else PLACEHOLDER
        diameter = ('%.2f' % product.x_diameter) if product.x_diameter else PLACEHOLDER
        lens_index = product.lens_index_id.name if product.lens_index_id else PLACEHOLDER

        category_label = (
            product.classification_id.name
            if product.classification_id
            else (product.categ_id.name if product.categ_id else PLACEHOLDER)
        )

        # "Thông tin bổ sung" — list accessories or "Không"
        extras = []
        if product.has_box:
            extras.append('Hộp')
        if product.has_cleaning_cloth:
            extras.append('Khăn lau')
        if product.has_warranty_card:
            extras.append('Thẻ bảo hành')
        if product.accessory_note:
            extras.append(product.accessory_note)
        extra_info = ', '.join(extras) if extras else 'Không'

        values = {
            'product': product,
            'name': product.display_name or product.name or '',
            'brand': product.brand_id.name if product.brand_id else '',
            'description': product.description_sale or PLACEHOLDER,
            'price': product.list_price or 0.0,
            'currency_symbol': currency.symbol if currency else '₫',
            'image_url': f"/product/image/{product.id}",

            # THÔNG TIN SẢN PHẨM (left column / right column)
            'ma_kinh': _or_placeholder(product.barcode or product.default_code),
            'sph': sph,
            'xuat_xu': _or_placeholder(product.country_id.name if product.country_id else ''),
            'cyl': cyl,
            'phan_loai': category_label,
            'add_val': add,
            'chiet_suat': lens_index,
            'duong_kinh': diameter,
            'vat_lieu': _or_placeholder(product._portal_get_material()),

            # THÔNG TIN SỬ DỤNG
            'thong_tin_bo_sung': extra_info,
            'huong_dan': product.x_guide or PLACEHOLDER,
            'bao_quan': product.x_preserve or PLACEHOLDER,
            'canh_bao': product.x_warning or PLACEHOLDER,
            'cong_dung': product.x_uses or PLACEHOLDER,
        }
        return request.render('vnop_product_portal.product_qr_page', values)

    @http.route(
        '/product/<int:product_id>',
        type='http', auth='public', methods=['GET'], csrf=False, sitemap=False,
    )
    def product_page(self, product_id, **_kwargs):
        return self._render_product(product_id)

    # Alias kept for backward compatibility with QR codes already pointing
    # at /product/qr/<id> (previous portal version).
    @http.route(
        '/product/qr/<int:product_id>',
        type='http', auth='public', methods=['GET'], csrf=False, sitemap=False,
    )
    def product_qr_page(self, product_id, **_kwargs):
        return self._render_product(product_id)

    @http.route(
        '/product/image/<int:product_id>',
        type='http', auth='public', methods=['GET'], csrf=False, sitemap=False,
    )
    def product_image(self, product_id, **_kwargs):
        """Serve product.template image_1920 publicly (sudo).
        product.template has no public read ACL by default, so /web/image
        returns the placeholder for anonymous users — this route bypasses that.
        """
        product = self._resolve_product(product_id)
        if not product or not product.image_1920:
            return request.not_found()
        attachment = (
            request.env['ir.attachment']
            .sudo()
            .search([
                ('res_model', '=', 'product.template'),
                ('res_id', '=', product.id),
                ('res_field', '=', 'image_1920'),
            ], limit=1)
        )
        mimetype = attachment.mimetype or 'image/png'
        return request.make_response(
            base64.b64decode(product.image_1920),
            headers=[
                ('Content-Type', mimetype),
                ('Cache-Control', 'public, max-age=3600'),
            ],
        )
