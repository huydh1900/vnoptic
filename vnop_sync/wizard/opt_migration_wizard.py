# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class OptMigrationWizard(models.TransientModel):
    """
    Wizard migrate dữ liệu product.opt → fields trực tiếp trên product.template.
    (Hướng B: 1 template = 1 bộ thông tin gọng, không dùng child model)
    """
    _name = 'opt.migration.wizard'
    _description = 'Migrate Opt Data → Template Fields (Hướng B)'

    migrate_all = fields.Boolean('Migrate tất cả sản phẩm Gọng', default=True)
    product_ids = fields.Many2many(
        'product.template',
        string='Sản phẩm cần migrate',
        domain=[('product_kind_ui', '=', 'opt')],
    )
    delete_opt_after = fields.Boolean(
        'Xoá product.opt sau khi migrate',
        default=False,
        help='Nên để False cho đến khi xác nhận dữ liệu migrate đúng.',
    )

    result_summary = fields.Text('Kết quả', readonly=True)
    state = fields.Selection([('draft', 'Chờ'), ('done', 'Xong')], default='draft')

    # Field mapping: field trên product.opt → field trên product.template
    FIELD_MAP = [
        ('season',                  'opt_season',                   'char'),
        ('model',                   'opt_model',                    'char'),
        ('serial',                  'opt_serial',                   'char'),
        ('oem_ncc',                 'opt_oem_ncc',                  'char'),
        ('sku',                     'opt_sku',                      'char'),
        ('color',                   'opt_color',                    'char'),
        ('gender',                  'opt_gender',                   'char'),
        ('temple_width',            'opt_temple_width',             'int'),
        ('lens_width',              'opt_lens_width',               'int'),
        ('lens_span',               'opt_lens_span',                'int'),
        ('lens_height',             'opt_lens_height',              'int'),
        ('bridge_width',            'opt_bridge_width',             'int'),
        ('color_front_id',          'opt_color_front_id',           'm2o'),
        ('color_temple_id',         'opt_color_temple_id',          'm2o'),
        ('color_lens_id',           'opt_color_lens_id',            'm2o'),
        ('frame_id',                'opt_frame_id',                 'm2o'),
        ('frame_type_id',           'opt_frame_type_id',            'm2o'),
        ('shape_id',                'opt_shape_id',                 'm2o'),
        ('ve_id',                   'opt_ve_id',                    'm2o'),
        ('temple_id',               'opt_temple_id',                'm2o'),
        ('material_ve_id',          'opt_material_ve_id',           'm2o'),
        ('material_temple_tip_id',  'opt_material_temple_tip_id',   'm2o'),
        ('material_lens_id',        'opt_material_lens_id',         'm2o'),
        ('materials_front_ids',     'opt_materials_front_ids',      'm2m'),
        ('materials_temple_ids',    'opt_materials_temple_ids',     'm2m'),
        ('coating_ids',             'opt_coating_ids',              'm2m'),
    ]

    def _build_tmpl_vals(self, opt):
        vals = {}
        for opt_field, tmpl_field, ftype in self.FIELD_MAP:
            raw = getattr(opt, opt_field, None)
            if ftype == 'm2o':
                if raw:
                    vals[tmpl_field] = raw.id
            elif ftype == 'm2m':
                if raw:
                    vals[tmpl_field] = [(6, 0, raw.ids)]
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
                ('product_kind_ui', '=', 'opt'),
                ('opt_ids', '!=', False),
            ])
        else:
            templates = self.product_ids.filtered(
                lambda t: t.product_kind_ui == 'opt' and t.opt_ids
            )

        if not templates:
            self.result_summary = 'Không có sản phẩm gọng nào có dữ liệu product.opt cần migrate.'
            self.state = 'done'
            return self._reopen()

        migrated = 0
        skipped = 0
        errors = 0
        ids_to_delete = []

        for tmpl in templates:
            opt = tmpl.opt_ids[0]
            try:
                vals = self._build_tmpl_vals(opt)
                if not vals:
                    skipped += 1
                    _logger.warning(f'Bỏ qua tmpl={tmpl.default_code}: product.opt id={opt.id} không có dữ liệu.')
                    continue

                tmpl.write(vals)
                migrated += 1
                ids_to_delete.extend(tmpl.opt_ids.ids)
                _logger.info(f'Migrate {tmpl.default_code} (tmpl_id={tmpl.id}) <- opt_id={opt.id}')
            except Exception as e:
                errors += 1
                _logger.error(f'Lỗi migrate tmpl={tmpl.default_code}: {e}')

        count_deleted = 0
        if self.delete_opt_after and ids_to_delete:
            try:
                self.env['product.opt'].browse(ids_to_delete).unlink()
                count_deleted = len(ids_to_delete)
            except Exception as e:
                _logger.error(f'Lỗi xóa product.opt: {e}')

        lines = [
            f'Tổng template gọng có dữ liệu cũ: {len(templates)}',
            f'Migrate thành công:                {migrated}',
            f'Bỏ qua (không có thông số):        {skipped}',
            f'Lỗi:                               {errors}',
        ]
        if count_deleted:
            lines.append(f'Đã xóa product.opt records:        {count_deleted}')
        lines.append('')
        if errors == 0 and skipped == 0:
            lines.append('✅ Migrate hoàn tất. Kiểm tra các tab Thông tin / Thiết kế / Chất liệu / Màu sắc / Kích thước Gọng.')
        else:
            lines.append('⚠️ Một số records bị bỏ qua hoặc lỗi. Xem log server.')

        self.result_summary = '\n'.join(lines)
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
