{
    'name': 'Product Sync from Server',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'depends': ['base', 'stock', 'product', 'account', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_sync_views.xml',
        'views/xnk_brand_views.xml',
        'views/xnk_warranty_views.xml',
        'views/product_tree_common_views.xml',
        'views/product_template_views.xml',
        'views/product_excel_import_views.xml',
        'views/product_group_views.xml',
        'data/ir_cron_data.xml',
    ],
    'external_dependencies': {
        'python': ['requests', 'Pillow', 'python-dotenv', 'openpyxl', 'xlsxwriter']
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
