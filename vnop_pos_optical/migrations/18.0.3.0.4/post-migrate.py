# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def _sync_pos_config_categories(env):
    pos_categories = env['product.category'].search([
        ('vnop_pos_category_id', '!=', False),
    ]).mapped('vnop_pos_category_id')
    configs = env['pos.config'].search([('name', 'ilike', 'Mắt kính')])
    configs.with_context(bypass_categories_forbidden_change=True).write({
        'iface_available_categ_ids': [(6, 0, pos_categories.ids)],
    })


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    env['product.category']._vnop_sync_pos_categories_from_products()
    _sync_pos_config_categories(env)
