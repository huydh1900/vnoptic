{
    'name': 'User Management Enhancement (VNOPTIC)',
    'version': '2.0',
    'summary': 'Theo dõi lịch sử thay đổi thông tin người dùng qua Chatter',
    'description': """
        Module mở rộng quản lý người dùng với tracking tự động.
        Sử dụng chức năng Chatter/Tracking có sẵn của Odoo.
        Các trường được theo dõi:
        - Tên, Đăng nhập, Email, Phone, Mobile
        - Trạng thái (active)
        - Nhóm quyền (groups_id)
        - Công ty (company_id, company_ids)
    """,
    'category': 'Administration',
    'author': 'Antigravity',
    'depends': ['base', 'mail'],
    'data': [],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
