{
    'name': 'Product Sync from Server',
    'version': '18.0.1.0.4',
    'category': 'Inventory',
    'depends': ['base', 'stock', 'product', 'purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/uom_data.xml',
        'data/product_category_data.xml',
        'data/product_brand_data.xml',
        'views/product_sync_views.xml',
        'views/product_brand_views.xml',
        'views/product_warranty_views.xml',
        'views/product_tree_common_views.xml',
        'views/product_category_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_supplier_views.xml',
        'views/product_template_kanban_views.xml',
        'views/product_group_views.xml',
        'views/product_lens_config_views.xml',
        'views/product_master_data_config_views.xml',
        'views/product_opt_lens_views.xml',
        'views/server_connector_views.xml',
        'views/vnop_sync_purchase_config_menus.xml',
    ],
    'external_dependencies': {
        'python': ['requests', 'Pillow', 'python-dotenv', 'openpyxl', 'xlsxwriter']
    },
    'assets': {
        'web.assets_backend': [
            'vnop_sync/static/src/scss/product_kanban_modern.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
