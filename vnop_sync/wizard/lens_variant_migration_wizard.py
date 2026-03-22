# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class LensVariantMigrationWizard(models.TransientModel):
    """
    Wizard migrate du lieu product.lens -> fields truc tiep tren product.template.
    (Huong B: moi API CID = 1 template = 1 default variant, lens specs la field thuan)

    Logic:
    - Voi moi template lens con du lieu product.lens, lay record dau tien (lens_ids[0])
      va copy cac field sang template.lens_sph_id / lens_cyl_id / lens_add / ... etc.
    - Sau migrate: tab "Thiet ke Trong", "Chat lieu Trong", "Tich hop Trong" se hien thi
      dung du lieu; tab "Du lieu Cu" se bien mat sau khi lens_ids bi xoa.
    """
    _name = 'lens.variant.migration.wizard'
    _description = 'Migrate Lens Data -> Template Fields (Huong B)'

    # Cu hinh
    migrate_all = fields.Boolean(
        'Migrate tat ca san pham Lens',
        default=True,
        help='Neu bat: migrate tat ca template lens con du lieu product.lens. '
             'Neu tat: chi migrate san pham da chon.'
    )
    product_ids = fields.Many2many(
        'product.template',
        string='San pham can migrate',
        domain=[('product_kind_ui', '=', 'lens')],
        help='Chi hieu luc khi "Migrate tat ca" bi tat.'
    )
    delete_lens_after = fields.Boolean(
        'Xoa product.lens sau khi migrate',
        default=False,
        help='Xoa product.lens records sau khi da copy du lieu sang template fields. '
             'Nen de False cho den khi xac nhan du lieu migrate dung.'
    )

    # Ket qua (readonly)
    result_summary = fields.Text('Ket qua', readonly=True)
    state = fields.Selection([('draft', 'Cho'), ('done', 'Xong')], default='draft')

    # Field mapping: field tren product.lens -> field tren product.template
    # Format: (lens_field, tmpl_field, field_type)
    FIELD_MAP = [
        ('sph_id',      'lens_sph_id',      'm2o'),
        ('cyl_id',      'lens_cyl_id',      'm2o'),
        ('lens_add',    'lens_add',         'float'),
        ('base_curve',  'lens_base_curve',  'float'),
        ('diameter',    'lens_diameter',    'int'),
        ('prism',       'lens_prism',       'char'),
        ('design1_id',  'lens_design1_id',  'm2o'),
        ('design2_id',  'lens_design2_id',  'm2o'),
        ('material_id', 'lens_material_id', 'm2o'),
        ('index_id',    'lens_index_id',    'm2o'),
        ('uv_id',       'lens_uv_id',       'm2o'),
        ('cl_hmc_id',   'lens_cl_hmc_id',   'm2o'),
        ('cl_pho_id',   'lens_cl_pho_id',   'm2o'),
        ('cl_tint_id',  'lens_cl_tint_id',  'm2o'),
        ('color_int',   'lens_color_int',   'char'),
        ('mir_coating', 'lens_mir_coating', 'char'),
        ('coating_ids', 'lens_coating_ids', 'm2m'),
    ]

    def _build_tmpl_vals(self, lens):
        """Tao dict vals cho product.template tu 1 product.lens record."""
        vals = {}
        for lens_field, tmpl_field, ftype in self.FIELD_MAP:
            raw = getattr(lens, lens_field, None)
            if ftype == 'm2o':
                if raw:
                    vals[tmpl_field] = raw.id
            elif ftype == 'm2m':
                if raw:
                    vals[tmpl_field] = [(6, 0, raw.ids)]
            elif ftype == 'float':
                if raw:
                    vals[tmpl_field] = float(raw)
            elif ftype == 'int':
                if raw:
                    vals[tmpl_field] = int(raw)
            elif ftype == 'char':
                if raw:
                    vals[tmpl_field] = raw
        return vals

    def action_migrate(self):
        self.ensure_one()

        if self.migrate_all:
            templates = self.env['product.template'].search([
                ('product_kind_ui', '=', 'lens'),
                ('lens_ids', '!=', False),
            ])
        else:
            templates = self.product_ids.filtered(
                lambda t: t.product_kind_ui == 'lens' and t.lens_ids
            )

        if not templates:
            self.result_summary = 'Khong co san pham lens nao co du lieu product.lens can migrate.'
            self.state = 'done'
            return self._reopen()

        migrated = 0
        skipped = 0
        errors = 0
        ids_to_delete = []

        for tmpl in templates:
            lens = tmpl.lens_ids[0]
            try:
                vals = self._build_tmpl_vals(lens)
                if not vals:
                    skipped += 1
                    _logger.warning(
                        f"Bo qua tmpl={tmpl.default_code}: "
                        f"product.lens id={lens.id} khong co du lieu nao."
                    )
                    continue

                tmpl.write(vals)
                migrated += 1
                ids_to_delete.extend(tmpl.lens_ids.ids)
                _logger.info(
                    f"Migrate {tmpl.default_code} (tmpl_id={tmpl.id}) "
                    f"<- lens_id={lens.id}: {list(vals.keys())}"
                )
            except Exception as e:
                errors += 1
                _logger.error(
                    f"Loi migrate tmpl={tmpl.default_code} "
                    f"(tmpl_id={tmpl.id}, lens_id={lens.id}): {e}"
                )

        count_deleted = 0
        if self.delete_lens_after and ids_to_delete:
            try:
                self.env['product.lens'].browse(ids_to_delete).unlink()
                count_deleted = len(ids_to_delete)
                _logger.info(f"Da xoa {count_deleted} product.lens records.")
            except Exception as e:
                _logger.error(f"Loi khi xoa product.lens: {e}")

        summary_lines = [
            f'Tong template lens co du lieu cu: {len(templates)}',
            f'Migrate thanh cong:               {migrated}',
            f'Bo qua (khong co thong so):       {skipped}',
            f'Loi:                              {errors}',
        ]
        if count_deleted:
            summary_lines.append(f'Da xoa product.lens records:      {count_deleted}')
        summary_lines.append('')
        if errors == 0 and skipped == 0:
            summary_lines.append(
                'Migrate hoan tat. Kiem tra tab "Thiet ke Trong" / '
                '"Chat lieu Trong" / "Tich hop Trong" tren san pham lens.'
            )
        else:
            summary_lines.append('Mot so records bi bo qua hoac loi. Xem log server.')

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
