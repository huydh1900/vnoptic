# -*- coding: utf-8 -*-
{
    'name': 'VNOPTIC Inventory Statistic',
    'version': '18.0.1.0.0',
    'category': 'Warehouse',
    'summary': 'Inventory Dashboard SPH x CYL',
    'description': "Inventory Statistic Dashboard for VNOPTIC",
    'author': 'VNOPTIC Team',
    'website': '',
    
    # Phụ thuộc vào các module gốc và module custom của dự án
    'depends': [
        'base',
        'stock',              # Để tích hợp vào menu Kho
        'product',            # Product views
        'vnop_sync',    # Lấy thông tin Brand, product_type, computed fields
        'vnoptic_product',    # Lấy thông tin SPH/CYL, Index (lens_ids, opt_ids)
    ],
    
    # Danh sách các file data (view, security, data...)
    'data': [
        'security/ir.model.access.csv',          # Phân quyền truy cập
        'views/inventory_statistic_view.xml',    # Giao diện dashboard
        'views/product_views.xml',              # View sản phẩm với filter
    ],
    
    # Cấu hình APP
    'installable': True,
    'application': False,  # <--- FALSE: Không hiện icon App ngoài màn hình chính (theo yêu cầu)
    'auto_install': False,
    'license': 'LGPL-3',
}
