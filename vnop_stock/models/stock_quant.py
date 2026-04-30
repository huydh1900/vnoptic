# -*- coding: utf-8 -*-
from odoo import api, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def get_lens_stock_matrix(self):
        """Return lens on-hand stock aggregated by SPH (column) × CYL (row).

        SPH/CYL lấy từ Selection của `product.template` (`_SPH_VALUES`,
        `_CYL_VALUES`). Trục ngang là SPH, trục dọc là CYL — theo đúng thứ tự
        khai báo trong selection.

        Structure::

            {
                'sph_axis': [{'id': str, 'name': str}, ...],  # columns
                'cyl_axis': [{'id': str, 'name': str}, ...],  # rows
                'matrix':   {cyl_key: {sph_key: qty}},
                'row_totals': {cyl_key: qty},
                'col_totals': {sph_key: qty},
                'grand_total': qty,
            }
        """
        Tmpl = self.env['product.template']
        sph_axis = [{'id': v, 'name': v} for v in Tmpl._SPH_VALUES]
        cyl_axis = [{'id': v, 'name': v} for v in Tmpl._CYL_VALUES]

        empty_result = {
            'sph_axis': sph_axis,
            'cyl_axis': cyl_axis,
            'matrix': {},
            'row_totals': {},
            'col_totals': {},
            'grand_total': 0.0,
        }

        self.env.cr.execute("""
            SELECT t.x_cyl AS cyl_key,
                   t.x_sph AS sph_key,
                   SUM(q.quantity) AS qty
              FROM stock_quant q
              JOIN stock_location l ON l.id = q.location_id
              JOIN product_product p ON p.id = q.product_id
              JOIN product_template t ON t.id = p.product_tmpl_id
             WHERE l.usage = 'internal'
               AND t.x_sph IS NOT NULL
               AND t.x_cyl IS NOT NULL
               AND t.active = TRUE
               AND p.active = TRUE
             GROUP BY t.x_cyl, t.x_sph
            HAVING SUM(q.quantity) <> 0
        """)
        rows = self.env.cr.fetchall()
        if not rows:
            return empty_result

        matrix = {}
        row_totals = {}
        col_totals = {}
        grand_total = 0.0

        for cyl_key, sph_key, qty in rows:
            qty = float(qty or 0.0)
            if not qty:
                continue
            matrix.setdefault(cyl_key, {})[sph_key] = qty
            row_totals[cyl_key] = row_totals.get(cyl_key, 0.0) + qty
            col_totals[sph_key] = col_totals.get(sph_key, 0.0) + qty
            grand_total += qty

        return {
            'sph_axis': sph_axis,
            'cyl_axis': cyl_axis,
            'matrix': matrix,
            'row_totals': row_totals,
            'col_totals': col_totals,
            'grand_total': grand_total,
        }
