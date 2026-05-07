# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

POS_CATEGORY_XML_IDS = [
    'vnop_pos_optical.pos_cat_frame',
    'vnop_pos_optical.pos_cat_frame_men',
    'vnop_pos_optical.pos_cat_frame_women',
    'vnop_pos_optical.pos_cat_frame_kids',
    'vnop_pos_optical.pos_cat_lens',
    'vnop_pos_optical.pos_cat_lens_single',
    'vnop_pos_optical.pos_cat_lens_progressive',
    'vnop_pos_optical.pos_cat_lens_blueblock',
    'vnop_pos_optical.pos_cat_sunglasses',
    'vnop_pos_optical.pos_cat_contact_lens',
    'vnop_pos_optical.pos_cat_contact_lens_solution',
    'vnop_pos_optical.pos_cat_accessories',
    'vnop_pos_optical.pos_cat_accessories_case',
    'vnop_pos_optical.pos_cat_accessories_cleaner',
    'vnop_pos_optical.pos_cat_service',
]

PARTNER_XML_IDS = [
    'vnop_pos_optical.partner_walkin_demo',
    'vnop_pos_optical.partner_retail_nguyen_van_a',
    'vnop_pos_optical.partner_retail_tran_thi_b',
    'vnop_pos_optical.partner_dealer_kinhthuoc_hadong',
    'vnop_pos_optical.partner_dealer_optical_haiphong',
    'vnop_pos_optical.partner_dealer_kinh_saigon',
]


def _unlink_xmlid_records(env, xmlids):
    for xmlid in xmlids:
        with env.cr.savepoint():
            record = env.ref(xmlid, raise_if_not_found=False)
            data = env['ir.model.data'].search([
                ('module', '=', xmlid.split('.')[0]),
                ('name', '=', xmlid.split('.')[1]),
            ], limit=1)
            if not record:
                data.unlink()
                continue
            try:
                record.unlink()
                data.unlink()
            except Exception as exc:
                _logger.warning("vnop_pos_optical: cannot delete sample record %s: %s", xmlid, exc)


def _sync_pos_config_categories(env):
    pos_categories = env['product.category'].search([
        ('vnop_pos_category_id', '!=', False),
    ]).mapped('vnop_pos_category_id')
    if not pos_categories:
        return

    configs = env['pos.config'].search([('name', 'ilike', 'Mắt kính')])
    configs.with_context(bypass_categories_forbidden_change=True).write({
        'iface_available_categ_ids': [(6, 0, pos_categories.ids)],
    })


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    _unlink_xmlid_records(env, PARTNER_XML_IDS)
    _unlink_xmlid_records(env, POS_CATEGORY_XML_IDS)
    env['product.category']._vnop_sync_pos_categories_from_products()
    _sync_pos_config_categories(env)
