# -*- coding: utf-8 -*-
"""
Wizard: Chuẩn hóa Lens – Xóa Variant & Attribute SPH/CYL/ADD
=============================================================
PHẦN 1 của quy trình chuẩn hóa lens (Final Structure):
- Xóa toàn bộ attribute_line_ids (SPH/CYL/ADD) khỏi lens templates
- Xóa variant dư, chỉ giữ 1 product_variant_id mặc định
- Báo cáo: số lens đã cleanup, attribute_lines đã xóa, variant đã xóa
"""
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LensCleanupWizard(models.TransientModel):
    _name = 'lens.cleanup.wizard'
    _description = 'Chuẩn hóa Lens – Xóa Variant & Attribute SPH/CYL/ADD'

    # ── Kết quả sau khi chạy ─────────────────────────────────────────────────
    state = fields.Selection(
        [('draft', 'Chưa chạy'), ('done', 'Hoàn thành')],
        default='draft', readonly=True
    )
    lens_count = fields.Integer('Lens đã xử lý', readonly=True)
    attr_removed = fields.Integer('Attribute lines đã xóa', readonly=True)
    variant_removed = fields.Integer('Variant dư đã xóa', readonly=True)
    design_created = fields.Integer('Design mới tạo (thông tin)', readonly=True)
    material_created = fields.Integer('Material mới tạo (thông tin)', readonly=True)
    log_text = fields.Text('Nhật ký chi tiết', readonly=True)

    # ── Tuỳ chọn ─────────────────────────────────────────────────────────────
    also_remove_sph_cyl_add_attrs = fields.Boolean(
        'Xóa luôn attribute SPH/CYL/ADD khỏi hệ thống',
        default=False,
        help='Nếu tick, sau khi xóa khỏi lens templates sẽ xóa tiếp bản ghi '
             'product.attribute SPH/CYL/ADD (cẩn thận nếu dùng cho sản phẩm khác)'
    )

    # ─────────────────────────────────────────────────────────────────────────
    def action_run_cleanup(self):
        """
        Bước 1: tìm tất cả lens templates.
        Bước 2: xóa attribute_line_ids.
        Bước 3: xóa variant dư (giữ 1 default variant).
        Bước 4: cập nhật stat fields.
        """
        self.ensure_one()

        lens_templates = self.env['product.template'].search(
            [('product_kind_ui', '=', 'lens')]
        )
        if not lens_templates:
            raise UserError(_('Không tìm thấy sản phẩm nào có product_kind_ui = "lens".'))

        total_lens = 0
        total_attr_removed = 0
        total_variant_removed = 0
        errors = []

        for template in lens_templates:
            try:
                # ── Bước 2: Xóa attribute lines ───────────────────────────
                attr_count = len(template.attribute_line_ids)
                if attr_count > 0:
                    template.with_context(tracking_disable=True).write({
                        'attribute_line_ids': [(5, 0, 0)]
                    })
                    total_attr_removed += attr_count
                    _logger.info(
                        f'🗑️ Lens tmpl={template.id} "{template.name}": '
                        f'xóa {attr_count} attribute lines'
                    )

                # ── Bước 3: Xóa variant dư ────────────────────────────────
                # Sau khi xóa attribute_line_ids, Odoo tự dọn variant.
                # Đợi recompute rồi check lại.
                self.env.cr.execute(
                    "SELECT id FROM product_product "
                    "WHERE product_tmpl_id = %s ORDER BY id",
                    (template.id,)
                )
                variant_ids = [r[0] for r in self.env.cr.fetchall()]

                if len(variant_ids) > 1:
                    keep_id = variant_ids[0]
                    to_delete_ids = variant_ids[1:]
                    try:
                        self.env['product.product'].browse(to_delete_ids).with_context(
                            tracking_disable=True, active_test=False
                        ).unlink()
                        total_variant_removed += len(to_delete_ids)
                        _logger.info(
                            f'🗑️ Lens tmpl={template.id}: xóa {len(to_delete_ids)} variant dư, '
                            f'giữ variant id={keep_id}'
                        )
                    except Exception as e:
                        err_msg = (
                            f'⚠️ template {template.id} ({template.name}): '
                            f'không unlink được {len(to_delete_ids)} variant: {e}'
                        )
                        errors.append(err_msg)
                        _logger.warning(err_msg)

                total_lens += 1

            except Exception as e:
                err_msg = f'❌ template {template.id} ({template.name}): {e}'
                errors.append(err_msg)
                _logger.error(err_msg)

        # ── Bước 4 (tuỳ chọn): xóa global attribute SPH/CYL/ADD ─────────
        if self.also_remove_sph_cyl_add_attrs:
            removed_global = self._remove_global_sph_cyl_add()
            _logger.info(f'🗑️ Đã xóa {removed_global} global attribute SPH/CYL/ADD records.')

        # ── Tổng kết ─────────────────────────────────────────────────────
        summary_lines = [
            f'✅ Cleanup hoàn tất!',
            f'──────────────────────────────',
            f'Lens templates đã xử lý : {total_lens}',
            f'Attribute lines đã xóa  : {total_attr_removed}',
            f'Variant dư đã xóa       : {total_variant_removed}',
        ]
        if errors:
            summary_lines.append(f'\n⚠️ Lỗi ({len(errors)}) :')
            summary_lines.extend(errors)

        log_text = '\n'.join(summary_lines)
        _logger.info(log_text)

        self.write({
            'state': 'done',
            'lens_count': total_lens,
            'attr_removed': total_attr_removed,
            'variant_removed': total_variant_removed,
            'log_text': log_text,
        })

        # Trả về cùng form để user xem kết quả
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'lens.cleanup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def _remove_global_sph_cyl_add(self):
        """Xóa product.attribute SPH/CYL/ADD nếu không còn được dùng ở đâu."""
        attrs = self.env['product.attribute'].search([
            ('name', 'in', ('SPH', 'CYL', 'ADD'))
        ])
        removed = 0
        for attr in attrs:
            lines_count = self.env['product.template.attribute.line'].search_count([
                ('attribute_id', '=', attr.id)
            ])
            if lines_count == 0:
                try:
                    attr.unlink()
                    removed += 1
                except Exception as e:
                    _logger.warning(f'⚠️ Không xóa được attribute {attr.name}: {e}')
        return removed

    def action_count_stats(self):
        """Đếm sơ bộ trước khi cleanup (dry-run info)."""
        self.ensure_one()
        lens_templates = self.env['product.template'].search(
            [('product_kind_ui', '=', 'lens')]
        )
        total_attr = sum(len(t.attribute_line_ids) for t in lens_templates)
        total_extra_var = sum(
            max(0, len(t.product_variant_ids) - 1) for t in lens_templates
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '📊 Thống kê trước cleanup',
                'message': (
                    f'Lens templates: {len(lens_templates)}\n'
                    f'Attribute lines cần xóa: {total_attr}\n'
                    f'Variant dư cần xóa: {total_extra_var}'
                ),
                'type': 'info',
                'sticky': True,
            }
        }
