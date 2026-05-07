# -*- coding: utf-8 -*-
{
    "name": "VNOP Sale Dashboard",
    "summary": "Dashboard bán hàng VNOptic - 6 chart phân tích doanh thu/công nợ/KPI",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "VNOPTIC",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "web",
        "sale_management",
        "account",
        "vnop_sale_channel",
    ],
    # vnop_sale_workflow is optional — menu KPI nhân viên chỉ visible khi module installed
    # TODO: enable vnop_sale_target_pivot_views.xml when vnop_sale_workflow is installed
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "views/vnop_sale_report_channel_views.xml",
        "views/vnop_sale_report_aging_views.xml",
        "views/sale_order_pivot_views.xml",
        "views/sale_order_line_pivot_views.xml",
        "views/dashboard_client_action.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "vnop_sale_dashboard/static/src/js/dashboard_kpi_tiles.js",
            "vnop_sale_dashboard/static/src/xml/dashboard_kpi_tiles.xml",
            "vnop_sale_dashboard/static/src/scss/dashboard.scss",
        ],
    },
    "installable": True,
    "application": False,
}
