# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from ..utils import lens_variant_utils

_logger = logging.getLogger(__name__)


class LensVariantMigrationToVariantWizard(models.TransientModel):
    _name = 'lens.variant.migration.to.variant.wizard'
    _description = 'Migrate Lens Data -> Variants (SPH/CYL/ADD)'

    migrate_all = fields.Boolean(
        'Migrate tat ca san pham Lens',
        default=True,
        help='Neu bat: migrate tat ca template lens co du lieu. '
             'Neu tat: chi migrate san pham da chon.'
    )
    product_ids = fields.Many2many(
        'product.template',
        string='San pham can migrate',
        domain=[('product_type', '=', 'lens')],
        help='Chi hieu luc khi "Migrate tat ca" bi tat.'
    )

    result_summary = fields.Text('Ket qua', readonly=True)
    state = fields.Selection([('draft', 'Cho'), ('done', 'Xong')], default='draft')

    def _iter_lens_specs(self, tmpl):
        if tmpl.lens_ids:
            for lens in tmpl.lens_ids:
                yield {
                    'sph': lens.sph_id.value if lens.sph_id else None,
                    'cyl': lens.cyl_id.value if lens.cyl_id else None,
                    'add': lens.lens_add or 0.0,
                }
            return

        # Fallback: use template fields if present
        yield {
            'sph': tmpl.lens_sph_id.value if tmpl.lens_sph_id else None,
            'cyl': tmpl.lens_cyl_id.value if tmpl.lens_cyl_id else None,
            'add': tmpl.lens_add or 0.0,
        }

    def _get_or_create_variant(self, tmpl, spec):
        sph = lens_variant_utils.format_power_value(spec.get('sph'))
        cyl = lens_variant_utils.format_power_value(spec.get('cyl'))
        if not sph or not cyl:
            return False

        add_val = lens_variant_utils.format_power_value(spec.get('add'))

        attr_sph = lens_variant_utils.get_or_create_attribute(self.env, 'SPH')
        attr_cyl = lens_variant_utils.get_or_create_attribute(self.env, 'CYL')
        attr_add = lens_variant_utils.get_or_create_attribute(self.env, 'ADD') if add_val else False

        val_sph = lens_variant_utils.get_or_create_attribute_value(self.env, attr_sph, sph)
        val_cyl = lens_variant_utils.get_or_create_attribute_value(self.env, attr_cyl, cyl)
        val_add = lens_variant_utils.get_or_create_attribute_value(self.env, attr_add, add_val) if attr_add else False

        lens_variant_utils.ensure_attribute_line(tmpl, attr_sph, [val_sph.id])
        lens_variant_utils.ensure_attribute_line(tmpl, attr_cyl, [val_cyl.id])
        if attr_add and val_add:
            lens_variant_utils.ensure_attribute_line(tmpl, attr_add, [val_add.id])

        value_ids = [val_sph.id, val_cyl.id]
        if val_add:
            value_ids.append(val_add.id)

        variant = lens_variant_utils.find_variant_by_values(tmpl, value_ids)
        if variant:
            return variant

        return lens_variant_utils.create_variant(tmpl, value_ids)

    def action_migrate(self):
        self.ensure_one()

        if self.migrate_all:
            templates = self.env['product.template'].search([
                ('product_type', '=', 'lens'),
            ])
        else:
            templates = self.product_ids.filtered(lambda t: t.product_type == 'lens')

        if not templates:
            self.result_summary = 'Khong co san pham lens nao de migrate.'
            self.state = 'done'
            return self._reopen()

        processed = 0
        created = 0
        skipped = 0
        errors = 0

        for tmpl in templates:
            processed += 1
            try:
                for spec in self._iter_lens_specs(tmpl):
                    variant = self._get_or_create_variant(tmpl, spec)
                    if not variant:
                        skipped += 1
                        continue
                    created += 1
            except Exception as e:
                errors += 1
                _logger.error(
                    f"Loi migrate variant tmpl_id={tmpl.id} default_code={tmpl.default_code}: {e}"
                )

        summary_lines = [
            f'Tong template lens:              {processed}',
            f'Variant tao moi/da co:          {created}',
            f'Bo qua (thieu SPH/CYL):         {skipped}',
            f'Loi:                            {errors}',
        ]
        self.result_summary = '\n'.join(summary_lines)
        self.state = 'done'
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
