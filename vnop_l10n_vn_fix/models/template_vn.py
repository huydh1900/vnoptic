# -*- coding: utf-8 -*-
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    # Fix l10n_vn template_vn.py referencing 'chart154' which does NOT exist
    # in l10n_vn/data/template/account.account-vn.csv (only chart1541/chart1542 exist).
    # The broken reference crashes stock_account post-init (_load_wip_accounts)
    # with: ValueError: External ID not found in the system: account.<id>_chart154
    #
    # Odoo merges all @template('vn', 'res.company') methods via dict.update()
    # in chart_template._get_chart_template_data, iterating methods in alphabetical
    # order (getmembers). The method name below sorts after '_get_vn_res_company'
    # so its value overwrites the broken one.
    @template('vn', 'res.company')
    def _get_vn_res_company_wip_fix(self):
        return {
            self.env.company.id: {
                'account_production_wip_account_id': 'chart1541',
            },
        }
