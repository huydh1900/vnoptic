{
    'name': 'User Change Log (VNOPTIC)',
    'version': '1.0',
    'summary': 'Ghi lại lịch sử thay đổi thông tin quan trọng của người dùng',
    'description': """
        Module ghi log khi thay đổi thông tin người dùng (res.users).
        Các trường theo dõi:
        - Trạng thái (active)
        - Nhóm quyền (groups_id)
        - Tên, Đăng nhập, Email
    """,
    'category': 'Administration',
    'author': 'Antigravity',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/user_change_log_view.xml',
        'views/res_users_view.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
