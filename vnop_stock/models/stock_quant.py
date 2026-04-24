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

        # Gộp aggregate vào 1 SQL: JOIN quant → product → template → location,
        # GROUP theo (lens_cyl_id, lens_sph_id). Không load template/product
        # vào Python, không phải map thủ công.
        self.env.cr.execute("""
            SELECT t.lens_cyl_id AS cyl_id,
                   t.lens_sph_id AS sph_id,
                   SUM(q.quantity) AS qty
              FROM stock_quant q
              JOIN stock_location l ON l.id = q.location_id
              JOIN product_product p ON p.id = q.product_id
              JOIN product_template t ON t.id = p.product_tmpl_id
             WHERE l.usage = 'internal'
               AND t.lens_sph_id IS NOT NULL
               AND t.lens_cyl_id IS NOT NULL
               AND t.active = TRUE
               AND p.active = TRUE
             GROUP BY t.lens_cyl_id, t.lens_sph_id
            HAVING SUM(q.quantity) <> 0
        """)
        rows = self.env.cr.fetchall()
        if not rows:
            return empty_result

        matrix = {}
        row_totals = {}
        col_totals = {}
        grand_total = 0.0

        for cyl_id, sph_id, qty in rows:
            qty = float(qty or 0.0)
            if not qty:
                continue
            matrix.setdefault(cyl_id, {})[sph_id] = qty
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
