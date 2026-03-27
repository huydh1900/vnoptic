{
    'name': 'Product Sync from Server',
    'version': '18.0.1.0.4',
    'category': 'Inventory',
    'depends': ['base', 'stock', 'product', 'purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/uom_data.xml',
        'data/product_category_data.xml',
        'data/product_brand_data.xml',
        'views/product_sync_views.xml',
        'views/product_brand_views.xml',
        'views/product_warranty_views.xml',
        'views/product_warranty_template_views.xml',
        'views/product_tree_common_views.xml',
        'views/product_category_views.xml',
        'views/product_template_views.xml',
        'views/product_group_views.xml',
        'views/product_lens_config_views.xml',
    ],
    'external_dependencies': {
        'python': ['requests', 'Pillow', 'python-dotenv', 'openpyxl', 'xlsxwriter']
    },
    'assets': {
        'web.assets_backend': [
            'vnop_sync/static/src/scss/preview_long_text.scss',
            'vnop_sync/static/src/js/preview_long_text.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
