# -*- coding: utf-8 -*-
{
    "name": "Đề nghị mua hàng",
    "depends": ["purchase", "mail", "vnop_contract"],
    "data": [
        "security/ir.model.access.csv",
        "data/purchase_offer_data.xml",
        "data/purchase_offer_actions.xml",
        "views/contract_views.xml",
        "views/contract_line_views.xml",
        "views/purchase_offer_views.xml",
    ],
}
