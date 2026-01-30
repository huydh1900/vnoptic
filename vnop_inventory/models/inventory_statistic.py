# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class InventoryStatistic(models.TransientModel):
    _name = 'vnoptic.inventory.statistic'
    _description = 'Inventory Statistic Dashboard'

    # 1. CÁC TRƯỜNG DỮ LIỆU (FIELDS)
    
    # --- Tên hiển thị (bắt buộc với một số view) ---
    display_name = fields.Char(default='Tồn Kho', compute='_compute_display_name')
    
    # --- Bộ lọc (Filters) ---
    sph_max = fields.Integer(string='SPH (4-20)', default=4, required=True, 
                            help="Nhập giá trị tuyệt đối. Ví dụ nhập 4 -> Phạm vi sẽ là 0..4 hoặc -4..0")
    
    cyl_max = fields.Integer(string='CYL (4-20)', default=4, required=True,
                            help="Nhập giá trị tuyệt đối cho CYL")
    
    sph_mode = fields.Selection([
        ('negative', 'Âm (-)'),       # SPH < 0, CYL < 0
        ('positive', 'Dương (+)'),    # SPH > 0, CYL > 0
        ('both', 'Cả hai (±)'),       # SPH -..+, CYL -..0 (hoặc theo input)
    ], string='Phạm vi SPH', default='negative', required=True)

    # --- Liên kết (Relational Fields) ---
    brand_id = fields.Many2one('product.brand', string='Thương hiệu')
    index_id = fields.Many2one('product.lens.index', string='Chiết suất mắt kính')

    # --- Kết quả hiển thị (Result Fields) ---
    html_matrix = fields.Html(string='Matrix Data', readonly=True, sanitize=False)
    
    total_qty = fields.Integer(string='Tổng Tồn Kho', readonly=True)
    good_qty = fields.Integer(string='Kho Đạt', readonly=True)
    defect_qty = fields.Integer(string='Kho Lỗi', readonly=True)

    # 2. LOGIC TÍNH TOÁN & XỬ LÝ (METHODS)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Tồn Kho"

    @api.model
    def default_get(self, fields_list):
        """Bảo đảm khi mở form lần đầu đã có bảng 4x4 trống (không hiện False)."""
        defaults = super().default_get(fields_list)
        # Lấy giá trị default hoặc fallback
        sph_max = defaults.get('sph_max', 4)
        cyl_max = defaults.get('cyl_max', 4)
        sph_mode = defaults.get('sph_mode', 'negative')

        sph_rows = self._generate_range_sph(sph_max, sph_mode)
        cyl_cols = self._generate_range_cyl(cyl_max, sph_mode)
        defaults['html_matrix'] = self._build_html_matrix(sph_rows, cyl_cols, {})
        defaults['total_qty'] = 0
        defaults['good_qty'] = 0
        defaults['defect_qty'] = 0
        return defaults

    @api.constrains('sph_max', 'cyl_max')
    def _check_max_range(self):
        """Validate SPH Max và CYL Max phải trong khoảng 4-20"""
        for rec in self:
            if rec.sph_max < 4 or rec.sph_max > 20:
                raise models.ValidationError(_("SPH Max phải từ 4 đến 20!"))
            if rec.cyl_max < 4 or rec.cyl_max > 20:
                raise models.ValidationError(_("CYL Max phải từ 4 đến 20!"))

    @api.model
    def create(self, vals):
        """Override create - không auto-generate để tránh ValidationError khi chưa chọn filter"""
        record = super(InventoryStatistic, self).create(vals)
        # Không tự động generate, user phải bấm nút "Thống kê"
        return record

    def action_generate_matrix(self):
        """
        Thống kê: Bắt buộc phải chọn đủ filter (brand, index, sph_max, cyl_max, sph_mode). CYL luôn là âm (0 đến -max). Tổng tồn kho chỉ tính trong phạm vi filter.
        """
        self.ensure_one()
        # Validate bắt buộc chọn đủ filter
        if not self.brand_id or not self.index_id or not self.sph_max or not self.cyl_max or not self.sph_mode:
            raise models.ValidationError(_("Bạn phải chọn đầy đủ Thương hiệu, Chiết suất, SPH (4-20), CYL (4-20), Phạm vi SPH thì mới thống kê!"))
        self.write({'html_matrix': False})

        # --- BƯỚC 1: LẤY DANH SÁCH LOCATIONS (ĐẠT / LỖI) ---
        Warehouse = self.env['stock.warehouse']
        field_wh_type = 'warehouse_type'
        if not hasattr(Warehouse, field_wh_type) and hasattr(Warehouse, 'x_warehouse_type'):
            field_wh_type = 'x_warehouse_type'
        good_wh_ids = Warehouse.search([(field_wh_type, 'in', [1, '1'])]).ids if hasattr(Warehouse, field_wh_type) else []
        defect_wh_ids = Warehouse.search([(field_wh_type, 'in', [2, '2'])]).ids if hasattr(Warehouse, field_wh_type) else []
        Location = self.env['stock.location']
        good_locs = Location.search([('warehouse_id', 'in', good_wh_ids), ('usage', '=', 'internal')])
        defect_locs = Location.search([('warehouse_id', 'in', defect_wh_ids), ('usage', '=', 'internal')])
        t_all_ids = tuple(good_locs.ids + defect_locs.ids) if (good_locs or defect_locs) else (-1,)
        _logger.info(f"🔍 DEBUG: good_locs={len(good_locs)}, defect_locs={len(defect_locs)}, t_all_ids={t_all_ids[:5] if len(t_all_ids) > 1 else t_all_ids}")

        # --- BƯỚC 2: QUERY DỮ LIỆU TỒN KHO ---
        params = {
            'brand_id': self.brand_id.id,
            'index_id': self.index_id.id,
            'loc_ids': t_all_ids
        }
        where_clause = "WHERE sq.location_id IN %(loc_ids)s"
        where_clause += " AND pt.brand_id = %(brand_id)s"
        where_clause += " AND pt.index_id = %(index_id)s"
        sql_query = f"""
            SELECT 
                CASE WHEN pl.sph ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN CAST(pl.sph AS NUMERIC) ELSE 0 END as sph_val,
                CASE WHEN pl.cyl ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN CAST(pl.cyl AS NUMERIC) ELSE 0 END as cyl_val,
                sq.location_id,
                SUM(sq.quantity) as qty
            FROM stock_quant sq
            JOIN product_product pp ON sq.product_id = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            JOIN product_lens pl ON pl.product_tmpl_id = pt.id
            {where_clause}
            GROUP BY 1, 2, 3
        """
        self.env.cr.execute(sql_query, params)
        query_results = self.env.cr.fetchall()
        _logger.info(f"🔍 DEBUG: Query trả về {len(query_results)} rows. Brand: {self.brand_id.name}, Index: {self.index_id.name}")
        _logger.info(f"🔍 DEBUG: SQL = {sql_query % params}")
        if query_results:
            _logger.info(f"🔍 DEBUG: Sample data: {query_results[:3]}")
        else:
            # Debug: Thử query không JOIN product_lens để xem có dữ liệu stock không
            test_query = f"SELECT COUNT(*) FROM stock_quant sq WHERE sq.location_id IN %(loc_ids)s"
            self.env.cr.execute(test_query, {'loc_ids': t_all_ids})
            stock_count = self.env.cr.fetchone()[0]
            _logger.warning(f"⚠️ DEBUG: Không có dữ liệu từ query chính. Test query: có {stock_count} stock_quant records trong locations.")
            # Test xem có product_lens records không
            test_lens = f"SELECT COUNT(*) FROM product_lens pl JOIN product_template pt ON pl.product_tmpl_id = pt.id WHERE pt.brand_id = %(brand_id)s AND pl.index_id = %(index_id)s"
            self.env.cr.execute(test_lens, params)
            lens_count = self.env.cr.fetchone()[0]
            _logger.warning(f"⚠️ DEBUG: Có {lens_count} product_lens records với brand={self.brand_id.name}, index={self.index_id.name}")

        # --- BƯỚC 3: XỬ LÝ DỮ LIỆU VÀ TẠO DATA MAP ---
        data_map = {}
        total_good = 0
        total_defect = 0
        for row in query_results:
            r_sph = round(float(row[0]), 2)
            r_cyl = round(float(row[1]), 2)
            r_loc_id = row[2]
            r_qty = row[3]
            # Chỉ lấy các giá trị đúng phạm vi filter
            sph_min = -float(self.sph_max) if self.sph_mode in ('negative', 'both') else 0.0
            sph_max = float(self.sph_max) if self.sph_mode in ('positive', 'both') else 0.0
            cyl_min = -float(self.cyl_max)
            cyl_max = 0.0
            if not (sph_min <= r_sph <= sph_max):
                continue
            if not (cyl_min <= r_cyl <= cyl_max):
                continue
            key = (r_sph, r_cyl)
            if key not in data_map:
                data_map[key] = {'good': 0, 'defect': 0}
            if r_loc_id in good_locs.ids:
                data_map[key]['good'] += r_qty
                total_good += r_qty
            elif r_loc_id in defect_locs.ids:
                data_map[key]['defect'] += r_qty
                total_defect += r_qty

        # --- BƯỚC 4: LUÔN SINH DẢI SỐ SPH THEO MODE, CYL LUÔN ÂM ---
        sph_rows = self._generate_range_sph(self.sph_max, self.sph_mode)
        cyl_cols = self._generate_range_cyl(self.cyl_max, 'negative')

        # --- BƯỚC 5: SINH HTML MA TRẬN ---
        html_content = self._build_html_matrix(sph_rows, cyl_cols, data_map)
        self.write({
            'html_matrix': html_content,
            'total_qty': total_good + total_defect,
            'good_qty': total_good,
            'defect_qty': total_defect
        })
        return True

    def action_reset_filter(self):
        """Reset tất cả bộ lọc về giá trị mặc định và tự động generate lại bảng 4x4 với số liệu = 0"""
        self.ensure_one()
        # Reset filter fields
        self.write({
            'sph_max': 4,
            'cyl_max': 4,
            'sph_mode': 'negative',
            'brand_id': False,
            'index_id': False
        })
        # Sinh lại bảng 4x4 toàn 0
        sph_rows = self._generate_range_sph(4, 'negative')
        cyl_cols = self._generate_range_cyl(4, 'negative')
        html_content = self._build_html_matrix(sph_rows, cyl_cols, {})
        self.write({
            'html_matrix': html_content,
            'total_qty': 0,
            'good_qty': 0,
            'defect_qty': 0
        })
        return True
    
    # 3. CÁC HÀM TIỆN ÍCH (UTILS / HELPERS)

    def _generate_range_sph(self, limit, mode):
        """
        Sinh danh sách SPH step 0.25
        Sort DESC (Từ cao xuống thấp) để hiển thị trục dọc đẹp (Số dương ở trên, âm dưới)
        """
        step = 0.25
        res = []
        limit = float(limit)
        
        if mode == 'negative':
            # Từ 0 xuống -limit (Ví dụ: 0, -0.25, ..., -4.00)
            curr = 0.0
            while curr >= -limit:
                res.append(curr)
                curr -= step
        elif mode == 'positive':
            # Từ 0 lên +limit
            curr = 0.0
            while curr <= limit:
                res.append(curr)
                curr += step
        else: # both
            # Từ -limit lên +limit
            curr = -limit
            while curr <= limit:
                res.append(curr)
                curr += step
                
        # Round 2 số thập phân để tránh lỗi float (ví dụ 0.300000004)
        return sorted([round(x, 2) for x in res], reverse=True)

    def _generate_range_cyl(self, limit, mode):
        """
        Sinh danh sách CYL step 0.25, luôn từ 0 đến -limit (chỉ âm, không dương)
        Sort ASC (0, -0.25, -0.5, ...)
        """
        step = 0.25
        res = []
        limit = float(limit)
        curr = 0.0
        while curr >= -limit:
            res.append(curr)
            curr -= step
        return [round(x, 2) for x in res]

    def _build_html_matrix(self, sph_rows, cyl_cols, data_map):
        """
        Luôn trả về bảng HTML, kể cả khi không có dữ liệu (không để False/None)
        """
        # Nếu không có dòng/cột, vẫn render bảng trống
        if not sph_rows:
            sph_rows = [""]
        if not cyl_cols:
            cyl_cols = [""]

        headers = "".join([
            f"<th style='min-width: 70px; width: 70px; max-width: 70px; white-space: nowrap; "
            f"background: #eee; text-align: center; position: sticky; top: 0; z-index: 8; "
            f"border: 1px solid #dee2e6; padding: 8px;'>{c}</th>" 
            for c in cyl_cols
        ])

        body_rows = ""
        for sph in sph_rows:
            body_rows += "<tr>"
            body_rows += (
                f"<th style='min-width: 70px; width: 70px; max-width: 70px; white-space: nowrap; "
                f"background: #eee; text-align: center; "
                f"border: 1px solid #dee2e6; padding: 8px;'>{sph}</th>"
            )
            for cyl in cyl_cols:
                key = (sph, cyl)
                val_data = data_map.get(key, {'good': 0, 'defect': 0})
                good = int(val_data['good'])
                defect = int(val_data['defect'])
                total = good + defect
                bg_style = ""
                if total > 0:
                    bg_style = "background-color: #e6f4ea;"
                # Nội dung hiển thị số tổng tồn kho
                cell_content = f"<span style='font-weight:bold;'>{total}</span>"
                # Tooltip chi tiết khi hover
                tooltip = (
                    f"CYL: {cyl}, SPH: {sph}\nTồn kho: {total}\nĐạt: {good}\nLỗi: {defect}"
                )
                body_rows += (
                    f"<td style='min-width: 70px; width: 70px; max-width: 70px; white-space: nowrap; "
                    f"text-align: center; border: 1px solid #ddd; padding: 8px; {bg_style}' title='{tooltip}'>"
                    f"<span>{cell_content}</span></td>"
                )
            body_rows += "</tr>"

        return f"""
        <div style="overflow: auto; max-width: 1650px; max-height: 850px; border: 2px solid #dee2e6;">
            <table style="border-collapse: separate; border-spacing: 0; table-layout: fixed;">
                <thead>
                    <tr>
                        <!-- Ô góc trên cùng bên trái - Sticky top khi scroll dọc -->
                        <th style="min-width: 80px; width: 80px; max-width: 80px; white-space: nowrap; background: #e9ecef; text-align: center; position: sticky; top: 0; z-index: 10; border: 1px solid #dee2e6; padding: 8px;">SPH \\ CYL</th>
                        {headers}
                    </tr>
                </thead>
                <tbody>
                    {body_rows}
                </tbody>
            </table>
        </div>
        """
