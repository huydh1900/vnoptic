# -*- coding: utf-8 -*-
{
    "name": "VNOptic - Hóa đơn điện tử mock",
    "summary": "Mock hóa đơn điện tử VN - PDF template + email (placeholder cho HĐĐT thật)",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "author": "VNOptic",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "account",
        "web",
        "vnop_amount_to_text",
    ],
    "data": [
        "data/paperformat.xml",
        "data/ir_sequence.xml",
        "reports/report_invoice_vn.xml",
        "reports/report_invoice_vn_template.xml",
        "data/mail_template.xml",
        "views/account_move_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
