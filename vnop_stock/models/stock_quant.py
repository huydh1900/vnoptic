# -*- coding: utf-8 -*-
from odoo import api, models


# Biểu thức Postgres tách suffix " S±x.xx/C±x.xx" khỏi tên template để gom
# các template cùng "mẫu mắt". Khác nhau ở SPH/CYL → cùng lens_key.
_PG_LENS_KEY_EXPR = (
    r"TRIM(regexp_replace(COALESCE(t.name->>'vi_VN', t.name->>'en_US'), "
    r"'\s*S[+-]?\d+(\.\d+)?/C[+-]?\d+(\.\d+)?\s*$', '', 'i'))"
)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def get_lens_classifications(self):
        """Trả về danh sách product.classification có category_type='lens'.

        Mỗi item: ``{'id': int, 'name': str, 'code': str}``.
        """
        Cls = self.env['product.classification'].sudo()
        # Chỉ hiển thị các nhóm có CYL (loạn thị) — SPH+CYL bắt buộc.
        records = Cls.search(
            [('category_type', '=', 'lens'), ('name', 'ilike', 'loạn')],
            order='name',
        )
        return [
            {'id': r.id, 'name': r.name or '', 'code': r.code or ''}
            for r in records
        ]

    @api.model
    def get_lens_models(self, classification_id=None):
        """Trả về danh sách "mẫu mắt" (TÊN MẮT) — gom các template cùng base name.

        Mỗi item: ``{'key': <base_name>, 'name': <base_name>, 'tmpl_count': N}``
        Sắp xếp theo tên.
        """
        params = []
        cls_filter = ''
        if classification_id:
            cls_filter = ' AND t.classification_id = %s'
            params.append(int(classification_id))

        self.env.cr.execute(
            f"""
            SELECT {_PG_LENS_KEY_EXPR} AS lens_key,
                   COUNT(*) AS tmpl_count
              FROM product_template t
             WHERE t.x_sph IS NOT NULL
               AND t.x_cyl IS NOT NULL
               AND t.active = TRUE
               {cls_filter}
             GROUP BY lens_key
             HAVING {_PG_LENS_KEY_EXPR} <> ''
             ORDER BY lens_key
            """,
            params,
        )
        return [
            {'key': key, 'name': key, 'tmpl_count': int(cnt)}
            for key, cnt in self.env.cr.fetchall()
        ]

    @api.model
    def get_lens_stock_matrix(self, lens_key=None, classification_id=None):
        """Return lens on-hand stock aggregated by SPH (row) × CYL (column).

        SPH/CYL lấy từ Selection của `product.template` (`_SPH_VALUES`,
        `_CYL_VALUES`). Trục đứng (rows) là SPH, trục ngang (cols) là CYL.

        Khi truyền ``lens_key`` (tên mẫu mắt rút gọn — xem ``get_lens_models``),
        chỉ tổng hợp tồn của các template thuộc mẫu đó. Khi ``lens_key`` rỗng,
        gộp toàn bộ template lens (hành vi cũ).

        Structure::

            {
                'sph_axis': [{'id': str, 'name': str}, ...],  # rows
                'cyl_axis': [{'id': str, 'name': str}, ...],  # cols
                'matrix':   {sph_key: {cyl_key: qty}},
                'row_totals': {sph_key: qty},
                'col_totals': {cyl_key: qty},
                'grand_total': qty,
                'lens_key': str | None,
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
            'lens_key': lens_key or None,
            'classification_id': int(classification_id) if classification_id else None,
        }

        params = []
        lens_filter_sql = ''
        if lens_key:
            lens_filter_sql = f" AND {_PG_LENS_KEY_EXPR} = %s"
            params.append(lens_key)
        if classification_id:
            lens_filter_sql += ' AND t.classification_id = %s'
            params.append(int(classification_id))

        self.env.cr.execute(
            f"""
            SELECT t.x_sph AS sph_key,
                   t.x_cyl AS cyl_key,
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
               {lens_filter_sql}
             GROUP BY t.x_sph, t.x_cyl
            HAVING SUM(q.quantity) <> 0
            """,
            params,
        )
        rows = self.env.cr.fetchall()
        if not rows:
            return empty_result

        matrix = {}
        row_totals = {}
        col_totals = {}
        grand_total = 0.0

        for sph_key, cyl_key, qty in rows:
            qty = float(qty or 0.0)
            if not qty:
                continue
            matrix.setdefault(sph_key, {})[cyl_key] = qty
            row_totals[sph_key] = row_totals.get(sph_key, 0.0) + qty
            col_totals[cyl_key] = col_totals.get(cyl_key, 0.0) + qty
            grand_total += qty

        return {
            'sph_axis': sph_axis,
            'cyl_axis': cyl_axis,
            'matrix': matrix,
            'row_totals': row_totals,
            'col_totals': col_totals,
            'grand_total': grand_total,
            'lens_key': lens_key or None,
            'classification_id': int(classification_id) if classification_id else None,
        }

    @api.model
    def action_open_lens_stock_cell(self, sph, cyl, lens_key=None, classification_id=None):
        """Mở list stock.quant đã filter theo SPH/CYL (+ lens_key, classification).

        Dùng từ matrix UI khi user click vào 1 ô — show breakdown tồn kho.
        """
        domain = [
            ('location_id.usage', '=', 'internal'),
            ('product_id.product_tmpl_id.x_sph', '=', sph),
            ('product_id.product_tmpl_id.x_cyl', '=', cyl),
            ('product_id.product_tmpl_id.active', '=', True),
            ('product_id.active', '=', True),
        ]
        if classification_id:
            domain.append(
                ('product_id.product_tmpl_id.classification_id', '=', int(classification_id))
            )
        if lens_key:
            # Resolve lens_key → template ids (PG regex tách suffix S±/C±).
            self.env.cr.execute(
                f"""
                SELECT t.id
                  FROM product_template t
                 WHERE t.x_sph IS NOT NULL
                   AND t.x_cyl IS NOT NULL
                   AND t.active = TRUE
                   AND {_PG_LENS_KEY_EXPR} = %s
                """,
                [lens_key],
            )
            tmpl_ids = [r[0] for r in self.env.cr.fetchall()]
            if not tmpl_ids:
                tmpl_ids = [0]  # ép domain rỗng nếu lens_key invalid
            domain.append(('product_id.product_tmpl_id', 'in', tmpl_ids))

        title_parts = [f'SPH {sph}', f'CYL {cyl}']
        if lens_key:
            title_parts.append(lens_key)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tồn kho — ' + ' · '.join(title_parts),
            'res_model': 'stock.quant',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
            'context': {
                'search_default_internal_loc': 1,
                'search_default_productgroup': 1,
            },
            'target': 'current',
        }
