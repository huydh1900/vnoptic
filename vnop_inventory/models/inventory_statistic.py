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
        """Override create để tự động generate ma trận 4×4 mặc định khi mở dashboard"""
        record = super(InventoryStatistic, self).create(vals)
        # Tự động generate ma trận với giá trị mặc định
        record.action_generate_matrix()
        return record

    def action_generate_matrix(self):
        """
        Khi người dùng bấm 'Thống kê', sinh bảng động theo các giá trị SPH/CYL thực tế trong kho,
        nhưng chỉ lấy các giá trị nằm trong phạm vi filter (4–20).
        Giao diện mặc định và reset vẫn giữ bảng 4x4 như cũ.
        """
        self.ensure_one()
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

        # --- BƯỚC 2: QUERY DỮ LIỆU TỒN KHO ---
        params = {
            'brand_id': self.brand_id.id,
            'index_id': self.index_id.id,
            'loc_ids': t_all_ids
        }
        where_clause = "WHERE sq.location_id IN %(loc_ids)s"
        if self.brand_id:
            where_clause += " AND pt.brand_id = %(brand_id)s"
        if self.index_id:
            where_clause += " AND pl.index_id = %(index_id)s"
        sql_query = f"""
            SELECT 
                CASE WHEN pl.sph ~ '^-?[0-9]+(\.[0-9]+)?$' THEN CAST(pl.sph AS NUMERIC) ELSE 0 END as sph_val,
                CASE WHEN pl.cyl ~ '^-?[0-9]+(\.[0-9]+)?$' THEN CAST(pl.cyl AS NUMERIC) ELSE 0 END as cyl_val,
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

        # --- BƯỚC 3: XỬ LÝ DỮ LIỆU VÀ TẠO DATA MAP ---
        data_map = {}
        total_good = 0
        total_defect = 0
        for row in query_results:
            # Luôn round về 2 số thập phân để key khớp với dải số sinh bảng
            r_sph = round(float(row[0]), 2)
            r_cyl = round(float(row[1]), 2)
            r_loc_id = row[2]
            r_qty = row[3]
            key = (r_sph, r_cyl)
            if key not in data_map:
                data_map[key] = {'good': 0, 'defect': 0}
            if r_loc_id in good_locs.ids:
                data_map[key]['good'] += r_qty
                total_good += r_qty
            elif r_loc_id in defect_locs.ids:
                data_map[key]['defect'] += r_qty
                total_defect += r_qty

        # --- BƯỚC 4: LUÔN SINH DẢI SỐ SPH/CYL TỪ 0 HOẶC -MAX ĐẾN MAX THEO FILTER ---
        sph_rows = self._generate_range_sph(self.sph_max, self.sph_mode)
        cyl_cols = self._generate_range_cyl(self.cyl_max, self.sph_mode)

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
        Sinh danh sách CYL step 0.25
        Cập nhật logic: CYL chạy theo Mode giống SPH (Âm thì ra Âm, Dương ra Dương)
        Sort ASC (Từ trái qua phải, nhỏ đến lớn hoặc 0 -> max)
        """
        step = 0.25
        res = []
        limit = float(limit)
        
        # Logic CYL theo yêu cầu mới
        if mode == 'negative':
            # Từ 0 xuống -limit (Ví dụ: 0, -0.25, ..., -4)
            # Trục ngang: thường hiển thị từ 0 sang trái hoặc sang phải.
            # Ta cứ list ra: [0, -0.25, -0.5 ...]
            curr = 0.0
            while curr >= -limit:
                res.append(curr)
                curr -= step
            # Với số âm, ta sort Desc (về mặt trị tuyệt đối thì tăng dần, nhưng giá trị toán học giảm dần)
            # Ví dụ hiển thị: 0 | -0.25 | -0.5 ...
            return [round(x, 2) for x in res] # [0, -0.25, -0.5...]
            
        elif mode == 'positive':
            # Từ 0 lên +limit
            curr = 0.0
            while curr <= limit:
                res.append(curr)
                curr += step
            return [round(x, 2) for x in res] # [0, 0.25, 0.5...]
            
        else: # both
            # Với CYL mà chọn Both thì sao?
            # Thường CYL ít khi vừa âm vừa dương trên 1 bảng. 
            # Giả sử theo logic: chạy từ 0 -> +Mask (Mặc định dương nếu both?)
            # Hoặc chạy cả 2? "CYL: vẫn theo phạm vi nhập" -> Giả sử 0 -> +Max
            # Tạm thời để 0 -> +Max nếu chọn Both.
            curr = 0.0
            while curr <= limit:
                res.append(curr)
                curr += step
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
