# -*- coding: utf-8 -*-

from odoo import _


def format_power_value(raw_val):
    if raw_val in (None, '', False):
        return False
    try:
        val = float(raw_val)
    except (TypeError, ValueError):
        return False

    if abs(val) < 0.0001:
        val = 0.0

    if val > 0:
        return f"+{val:.2f}"
    return f"{val:.2f}"


def build_lens_template_key(cid, index_code, material_code, coating_codes, diameter, brand_code):
    coating_part = ','.join(sorted([c for c in (coating_codes or []) if c]))
    parts = [cid, index_code, material_code, coating_part, diameter, brand_code]
    return '|'.join([(str(p).strip().lower() if p is not None else '') for p in parts])


def get_or_create_attribute(env, name, create_variant='dynamic'):
    attribute = env['product.attribute'].search([('name', '=', name)], limit=1)
    if attribute:
        return attribute

    return env['product.attribute'].create({
        'name': name,
        'create_variant': create_variant,
    })


def get_or_create_attribute_value(env, attribute, value_name):
    value = env['product.attribute.value'].search([
        ('attribute_id', '=', attribute.id),
        ('name', '=', value_name),
    ], limit=1)
    if value:
        return value

    return env['product.attribute.value'].create({
        'attribute_id': attribute.id,
        'name': value_name,
    })


def ensure_attribute_line(template, attribute, value_ids):
    line = template.attribute_line_ids.filtered(lambda l: l.attribute_id.id == attribute.id)
    if line:
        existing = set(line.value_ids.ids)
        missing = [vid for vid in value_ids if vid not in existing]
        if missing:
            line.write({'value_ids': [(4, vid) for vid in missing]})
        return line

    return template.env['product.template.attribute.line'].create({
        'product_tmpl_id': template.id,
        'attribute_id': attribute.id,
        'value_ids': [(6, 0, value_ids)],
    })


def find_variant_by_values(template, value_ids):
    target = set(value_ids)
    for variant in template.product_variant_ids:
        variant_vals = set(variant.product_template_attribute_value_ids.product_attribute_value_id.ids)
        if variant_vals == target:
            return variant
    return False


def create_variant(template, value_ids):
    return template.env['product.product'].create({
        'product_tmpl_id': template.id,
        'product_template_attribute_value_ids': [(6, 0, value_ids)],
    })
