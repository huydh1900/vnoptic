{
    'name': 'Product Sync from Server',
    'version': '18.0.1.0.1',
    'category': 'Inventory',
    'depends': ['base', 'stock', 'product', 'account', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_sync_views.xml',
        'views/product_brand_views.xml',
        'views/product_warranty_views.xml',
        'views/product_warranty_template_views.xml',
        'views/product_tree_common_views.xml',
        'views/product_template_views.xml',
        'wizard/product_excel_import_views.xml',
        'wizard/lens_variant_migration_wizard_views.xml',
        'wizard/lens_variant_migration_to_variant_views.xml',
        'wizard/opt_migration_wizard_views.xml',
        'views/product_group_views.xml',
        'views/product_lens_config_views.xml',
        'data/ir_cron_data.xml',
    ],
    'external_dependencies': {
        'python': ['requests', 'Pillow', 'python-dotenv', 'openpyxl', 'xlsxwriter']
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
