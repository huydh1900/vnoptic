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
<<<<<<< Updated upstream
        Hàm chính được gọi khi nhấn nút 'Thống kê'
        1. Tìm các Location thuộc Kho Đạt và Kho Lỗi.
        2. Sinh danh sách dải số SPH và CYL.
        3. Query trực tiếp SQL để lấy tồn kho.
        4. Xây dựng bảng HTML và gán vào field html_matrix.
=======
        ... (giữ nguyên logic gốc)
>>>>>>> Stashed changes
        """
        self.ensure_one()
        # Xóa nội dung HTML cũ để tránh nhân bản bảng khi người dùng bấm nhiều lần
        self.write({'html_matrix': False})
        
<<<<<<< Updated upstream
=======
        # --- BƯỚC Debug: Log số lượng Brand và Chiết suất đang có trong DB ---
        brands = self.env['product.brand'].search_count([])
        indexes = self.env['product.lens.index'].search_count([])
        _logger.info(f"🔍 DEBUG VNOPTIC: Thấy {brands} Brands và {indexes} Chiết suất trong Database.")
        if brands == 0:
            _logger.warning("⚠️ CẢNH BÁO: Không tìm thấy Thương hiệu nào! Vui lòng kiểm tra lại quá trình Sync.")
        # -------------------------------------------------------------
        
>>>>>>> Stashed changes
        #  BƯỚC 1: LẤY DANH SÁCH LOCATIONS (ĐẠT / LỖI) 
        # Logic: Dựa vào field warehouse_type (hoặc x_warehouse_type) trong stock.warehouse
        # 1 = Đạt, 2 = Lỗi
        
        Warehouse = self.env['stock.warehouse']
        field_wh_type = 'warehouse_type'
        
        # Kiểm tra xem field có tồn tại không (đề phòng trường hợp chưa tạo hoặc sai tên)
        # Ưu tiên 'warehouse_type', nếu không có thì thử 'x_warehouse_type'
        if not hasattr(Warehouse, field_wh_type) and hasattr(Warehouse, 'x_warehouse_type'):
            field_wh_type = 'x_warehouse_type'
            
        # Tìm danh sách Warehouse ID
        # Lưu ý: search trả về recordset, .ids trả về list id
        good_wh_ids = []
        defect_wh_ids = []
        
        if hasattr(Warehouse, field_wh_type):
            good_wh_ids = Warehouse.search([(field_wh_type, 'in', [1, '1'])]).ids
            defect_wh_ids = Warehouse.search([(field_wh_type, 'in', [2, '2'])]).ids
        
        # Tìm tất cả Internal Location (usage='internal') thuộc các warehouse trên
        Location = self.env['stock.location']
        good_locs = Location.search([('warehouse_id', 'in', good_wh_ids), ('usage', '=', 'internal')])
        defect_locs = Location.search([('warehouse_id', 'in', defect_wh_ids), ('usage', '=', 'internal')])

        # Chuyển sang tuple để dùng trong câu lệnh SQL IN (...)
        # Nếu list rỗng thì gán (-1) để SQL không lỗi cú pháp
        t_good_ids = tuple(good_locs.ids) if good_locs else (-1,)
        t_defect_ids = tuple(defect_locs.ids) if defect_locs else (-1,)
        t_all_ids = tuple(good_locs.ids + defect_locs.ids) if (good_locs or defect_locs) else (-1,)

        # --- BƯỚC 2: SINH DẢI SỐ SPH VÀ CYL ---
        sph_rows = self._generate_range_sph(self.sph_max, self.sph_mode)
        cyl_cols = self._generate_range_cyl(self.cyl_max, self.sph_mode)

        # --- BƯỚC 3: QUERY DỮ LIỆU TỒN KHO TỪ DATABASE ---
        # Ta dùng SQL Query trực tiếp vì:
        # 1. Performance nhanh hơn ORM.
        # 2. Cần ép kiểu (CAST) trường SPH/CYL từ text sang số để group chính xác.
        
        # Chuẩn bị tham số cho query
        params = {
            'brand_id': self.brand_id.id,
            'index_id': self.index_id.id,
            'loc_ids': t_all_ids
        }
        
        # Xây dựng điều kiện WHERE động
        where_clause = "WHERE sq.location_id IN %(loc_ids)s"
        if self.brand_id:
            where_clause += " AND pt.brand_id = %(brand_id)s" # Brand nằm ở product.template
        if self.index_id:
            where_clause += " AND pl.index_id = %(index_id)s" # Index nằm ở product.lens

        # Câu lệnh SQL
        # Regex '^-?[0-9]+(\.[0-9]+)?$' dùng để check xem chuỗi có phải là số không
        # Nếu là số -> CAST sang NUMERIC
        # Nếu không -> Trả về 0
        sql_query = f"""
            SELECT 
                CASE WHEN pl.sph ~ '^-?[0-9]+(\.[0-9]+)?$' THEN CAST(pl.sph AS NUMERIC) ELSE 0 END as sph_val,
                CASE WHEN pl.cyl ~ '^-?[0-9]+(\.[0-9]+)?$' THEN CAST(pl.cyl AS NUMERIC) ELSE 0 END as cyl_val,
                sq.location_id,
                SUM(sq.quantity) as qty
            FROM stock_quant sq
            JOIN product_product pp ON sq.product_id = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
<<<<<<< Updated upstream
            JOIN product_lens pl ON pl.product_id = pp.id
=======
            JOIN product_lens pl ON pl.product_tmpl_id = pt.id
>>>>>>> Stashed changes
            {where_clause}
            GROUP BY 1, 2, 3
        """
        
        self.env.cr.execute(sql_query, params)
        query_results = self.env.cr.fetchall()

        # --- BƯỚC 4: XỬ LÝ DỮ LIỆU VÀ TẠO DATA MAP ---
        # Data Map: Key=(sph, cyl), Value={'good': 0, 'defect': 0}
        data_map = {}
        total_good = 0
        total_defect = 0

        for row in query_results:
            r_sph = float(row[0])
            r_cyl = float(row[1])
            r_loc_id = row[2]
            r_qty = row[3]
            
            # Key để truy xuất: (SPH, CYL)
            key = (r_sph, r_cyl)
            
            if key not in data_map:
                data_map[key] = {'good': 0, 'defect': 0}
            
            # Phân loại vào Đạt hay Lỗi dựa trên Location ID
            if r_loc_id in good_locs.ids:
                data_map[key]['good'] += r_qty
                total_good += r_qty
            elif r_loc_id in defect_locs.ids:
                data_map[key]['defect'] += r_qty
                total_defect += r_qty
                
        # --- BƯỚC 5: SINH HTML MA TRẬN ---
        html_content = self._build_html_matrix(sph_rows, cyl_cols, data_map)
        
        # --- BƯỚC 6: LƯU KẾT QUẢ VÀO DATABASE ---
        # Note: Vì là TransientModel nên dữ liệu này chỉ tạm thời,
        # nhưng cần write để view tự cập nhật lại.
        self.write({
            'html_matrix': html_content,
            'total_qty': total_good + total_defect,
            'good_qty': total_good,
            'defect_qty': total_defect
        })

        # Button type="object" tự reload record, không cần trả về action (tránh sinh thêm view)
        return True

    def action_reset_filter(self):
        """Reset tất cả bộ lọc về giá trị mặc định và tự động generate lại bảng 4x4"""
        self.ensure_one()
        self.write({
            'sph_max': 4,
            'cyl_max': 4,
            'sph_mode': 'negative',
            'brand_id': False,
            'index_id': False,
            'total_qty': 0,
            'good_qty': 0,
            'defect_qty': 0,
        })
        self.action_generate_matrix()
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
<<<<<<< Updated upstream
                good = val_data['good']
                defect = val_data['defect']
                bg_style = ""
                cell_content = ""
                if good > 0:
                    bg_style = "background-color: #e6f4ea;"
                    cell_content += f"<span style='color: #28a745; font-weight: bold;'>{int(good)}</span>"
                if defect > 0:
                    if cell_content: cell_content += " | "
                    cell_content += f"<span style='color: #dc3545; font-weight: bold;'>{int(defect)}</span>"
                if not cell_content:
                    cell_content = "<span style='color: #ddd;'>-</span>"
                body_rows += (
                    f"<td style='min-width: 70px; width: 70px; max-width: 70px; white-space: nowrap; "
                    f"text-align: center; border: 1px solid #ddd; padding: 8px; {bg_style}'>"
                    f"{cell_content}</td>"
=======
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
>>>>>>> Stashed changes
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
