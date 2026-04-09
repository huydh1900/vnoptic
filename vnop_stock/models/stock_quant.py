# -*- coding: utf-8 -*-
from odoo import api, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def get_lens_stock_matrix(self):
        """Return lens on-hand stock aggregated by SPH (column) × CYL (row).

        Trục ngang (SPH - độ cận) và trục dọc (CYL - độ loạn) được lấy từ
        toàn bộ bản ghi `product.lens.power` có `power_type` tương ứng,
        sắp giảm dần theo value (0 → âm dần). Ma trận luôn hiển thị full
        grid theo master data; ô không có tồn kho sẽ bỏ trống.

        Structure::

            {
                'sph_axis': [{'id': int, 'name': str, 'value': float}, ...],  # columns
                'cyl_axis': [{'id': int, 'name': str, 'value': float}, ...],  # rows
                'matrix':   {cyl_id: {sph_id: qty}},
                'row_totals': {cyl_id: qty},
                'col_totals': {sph_id: qty},
                'grand_total': qty,
            }
        """
        Power = self.env['product.lens.power']
        # Sort giảm dần theo value để hiển thị 0 → âm dần
        sph_records = Power.search(
            [('power_type', '=', 'sph')], order='value desc'
        )
        cyl_records = Power.search(
            [('power_type', '=', 'cyl')], order='value desc'
        )

        def _serialize(rec):
            return {'id': rec.id, 'name': rec.name, 'value': rec.value}

        sph_axis = [_serialize(r) for r in sph_records]
        cyl_axis = [_serialize(r) for r in cyl_records]

        empty_result = {
            'sph_axis': sph_axis,
            'cyl_axis': cyl_axis,
            'matrix': {},
            'row_totals': {},
            'col_totals': {},
            'grand_total': 0.0,
        }

        Template = self.env['product.template']
        templates = Template.search([
            ('lens_sph_id', '!=', False),
            ('lens_cyl_id', '!=', False),
        ])
        if not templates:
            return empty_result

        # Map product.product -> (sph_id, cyl_id)
        products = self.env['product.product'].search([
            ('product_tmpl_id', 'in', templates.ids),
        ])
        prod_to_axes = {
            p.id: (
                p.product_tmpl_id.lens_sph_id.id if p.product_tmpl_id.lens_sph_id else False,
                p.product_tmpl_id.lens_cyl_id.id if p.product_tmpl_id.lens_cyl_id else False,
            )
            for p in products
        }
        if not prod_to_axes:
            return empty_result

        # Aggregate on-hand quantity per product across internal locations
        groups = self.env['stock.quant'].read_group(
            domain=[
                ('product_id', 'in', list(prod_to_axes.keys())),
                ('location_id.usage', '=', 'internal'),
            ],
            fields=['product_id', 'quantity:sum'],
            groupby=['product_id'],
        )

        matrix = {}
        row_totals = {}
        col_totals = {}
        grand_total = 0.0

        for g in groups:
            qty = g.get('quantity') or 0.0
            if not qty:
                continue
            prod_id = g['product_id'][0]
            sph_id, cyl_id = prod_to_axes.get(prod_id, (False, False))
            if not sph_id or not cyl_id:
                continue
            matrix.setdefault(cyl_id, {})
            matrix[cyl_id][sph_id] = matrix[cyl_id].get(sph_id, 0.0) + qty
            row_totals[cyl_id] = row_totals.get(cyl_id, 0.0) + qty
            col_totals[sph_id] = col_totals.get(sph_id, 0.0) + qty
            grand_total += qty

        return {
            'sph_axis': sph_axis,
            'cyl_axis': cyl_axis,
            'matrix': matrix,
            'row_totals': row_totals,
            'col_totals': col_totals,
            'grand_total': grand_total,
        }
