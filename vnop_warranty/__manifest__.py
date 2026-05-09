{
    'name': 'VNOptic - Bảo hành',
    'version': '18.0.1.1.0',
    'category': 'Sales',
    'summary': 'Đăng ký + tra cứu bảo hành (MVP)',
    'depends': [
        'vnop_sync',
        'vnop_product_portal',
        'sale_management',
        'website',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_warranty_views.xml',
        'views/warranty_registration_views.xml',
        'views/sale_order_views.xml',
        'views/menu.xml',
        'templates/website_templates.xml',
        'templates/warranty_label_print.xml',
    ],
    'external_dependencies': {
        'python': ['qrcode'],
    },
    'license': 'LGPL-3',
    'application': False,
    'installable': True,
}
