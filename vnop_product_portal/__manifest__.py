# -*- coding: utf-8 -*-
{
    'name': 'Product QR Portal',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Public product detail page accessible via QR code',
    'description': """
Generate a QR code per product that opens a public page showing the product's
key information (name, brand, category, country, material, serial,
specification, price, uses, guide, warning, preserve).
The QR points to an Odoo controller served by this module.
""",
    'depends': ['base', 'product', 'vnop_sync'],
    'data': [
        'views/product_portal_templates.xml',
        'views/product_template_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vnop_product_portal/static/src/qr_clickable/qr_clickable.js',
            'vnop_product_portal/static/src/qr_clickable/qr_clickable.xml',
            'vnop_product_portal/static/src/qr_clickable/qr_clickable.scss',
        ],
    },
    'external_dependencies': {
        'python': ['qrcode', 'openpyxl'],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
