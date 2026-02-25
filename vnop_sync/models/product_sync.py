# -*- coding: utf-8 -*-
import logging
import os
import requests
import urllib3
from collections import defaultdict
from odoo import models, fields, api, _
from odoo.exceptions import UserError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_logger = logging.getLogger(__name__)

class ProductSync(models.Model):
    _name = 'product.sync'
    _description = 'Product Synchronization'
    _order = 'last_sync_date desc'

    name = fields.Char('Tên đồng bộ', required=True, default='Đồng bộ sản phẩm')
    last_sync_date = fields.Datetime('Ngày đồng bộ cuối', readonly=True)
    sync_status = fields.Selection([
        ('never', 'Chưa đồng bộ'),
        ('in_progress', 'Đang đồng bộ'),
        ('success', 'Thành công'),
        ('error', 'Lỗi')])
    sync_log = fields.Text('Nhật ký', readonly=True)

    total_synced = fields.Integer('Tổng sản phẩm đã sync', readonly=True)
    total_failed = fields.Integer('Tổng thất bại', readonly=True)
    lens_count = fields.Integer('Sản phẩm Mắt', readonly=True)
    opts_count = fields.Integer('Sản phẩm Gọng', readonly=True)
    other_count = fields.Integer('Sản phẩm khác', readonly=True)

    progress = fields.Float('Tiến độ (%)', readonly=True, compute='_compute_progress')

    @api.depends('total_synced', 'total_failed')
    def _compute_progress(self):
        for record in self:
            total = record.total_synced + record.total_failed
            record.progress = (record.total_synced / total * 100) if total > 0 else 0

    @api.model
    def _load_env(self):
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os.environ.setdefault(key.strip(), value.strip())
            except Exception as e:
                _logger.warning(f"Could not load .env file: {e}")

    @api.model
    def _get_api_config(self):
        self._load_env()
        
        base_url = os.getenv('SPRING_BOOT_BASE_URL')
        username = os.getenv('SPRINGBOOT_SERVICE_USERNAME')
        password = os.getenv('SPRINGBOOT_SERVICE_PASSWORD')

        # Kiểm tra nếu thiếu cấu hình bắt buộc
        if not all([base_url, username, password]):
            missing = []
            if not base_url: missing.append('SPRING_BOOT_BASE_URL')
            if not username: missing.append('SPRINGBOOT_SERVICE_USERNAME')
            if not password: missing.append('SPRINGBOOT_SERVICE_PASSWORD')
            raise UserError(_("Thiếu cấu hình môi trường bắt buộc: %s. "
                              "Vui lòng kiểm tra file .env") % ", ".join(missing))

        return {
            'base_url': base_url,
            'login_endpoint': os.getenv('API_LOGIN_ENDPOINT', '/api/auth/service-token'),
            'lens_endpoint': os.getenv('API_LENS_ENDPOINT', '/api/xnk/lens'),
            'opts_endpoint': os.getenv('API_OPTS_ENDPOINT', '/api/xnk/opts'),
            'types_endpoint': os.getenv('API_TYPES_ENDPOINT', '/api/xnk/types'),
            'service_username': username,
            'service_password': password,
            'ssl_verify': os.getenv('SSL_VERIFY', 'False').lower() == 'true',
            'login_timeout': int(os.getenv('LOGIN_TIMEOUT', '30')),
            'api_timeout': int(os.getenv('API_TIMEOUT', '300')),
        }

    def _get_access_token(self):
        config = self._get_api_config()
        login_url = f"{config['base_url']}{config['login_endpoint']}"
        try:
            _logger.info(f"🔐 Getting token from: {login_url}")
            response = requests.post(
                login_url,
                json={'username': config['service_username'], 'password': config['service_password']},
                verify=config['ssl_verify'], timeout=config['login_timeout']
            )
            response.raise_for_status()
            token = response.json().get('token')
            if not token: raise UserError(_('Login failed: No token received'))
            return token
        except Exception as e:
            raise UserError(_(f"Authentication failed: {str(e)}"))

    def _fetch_paged_api(self, endpoint, token, page=0, size=100):
        config = self._get_api_config()
        url = f"{config['base_url']}{endpoint}?page={page}&size={size}"
        try:
            response = requests.get(
                url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                verify=config['ssl_verify'], timeout=config['api_timeout']
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise UserError(_(f"API request failed: {str(e)}"))

    def _fetch_all_items(self, endpoint, token, label, limit=None):
        items = []
        page = 0
        total_elements = 0
        config = self._get_api_config()
        
        _logger.info(f"🔍 [DEBUG] Bắt đầu lấy dữ liệu {label} từ: {config['base_url']}{endpoint}")
        
        while True:
            res = self._fetch_paged_api(endpoint, token, page, 100)
            
            # Log metadata của trang đầu tiên để debug
            if page == 0:
                debug_res = {k: v for k, v in res.items() if k != 'content'}
                _logger.info(f"🔍 [DEBUG] Metadata API {label} (Trang 0): {debug_res}")
            
            content = res.get('content', [])
            if not content: break
            items.extend(content)
            
            total_elements = res.get('totalElements', 0)
            total_pages = res.get('totalPages', 1)
            
            _logger.info(f"📦 {label}: Trang {page + 1}/{total_pages}, Lấy được {len(content)} bản ghi (Tổng đã lấy: {len(items)}/{total_elements})")
            
            if limit and len(items) >= limit:
                return items[:limit]
            
            page += 1
            if page >= total_pages: break
            
        if total_elements > len(items) and not limit:
            _logger.warning(f"⚠️ Chú ý: API báo có {total_elements} bản ghi {label} nhưng chỉ lấy được {len(items)}. Kiểm tra lại tham số size hoặc server-side pagination.")
            
        return items

    def _preload_all_data(self):
        _logger.info("📦 Pre-loading existing data...")
        cache = {'products': {}, 'categories': {}, 'suppliers': {}, 'taxes': {}, 'groups': {}, 'groups_by_id': {}, 'statuses': {}}
        
        # Products
        for p in self.env['product.template'].search_read([('default_code', '!=', False)], ['id', 'default_code']):
            cache['products'][p['default_code']] = p['id']
            
        # Categories
        for c in self.env['product.category'].search_read([], ['id', 'name', 'parent_id']):
            pid = c['parent_id'][0] if c['parent_id'] else False
            cache['categories'][(c['name'], pid)] = c['id']

        # Suppliers
        for s in self.env['res.partner'].search_read([('ref', '!=', False)], ['id', 'ref']):
            cache['suppliers'][s['ref'].upper()] = s['id']
            
        # Taxes (Purchase taxes only)
        for t in self.env['account.tax'].search_read([('type_tax_use', '=', 'purchase')], ['id', 'name']):
            cache['taxes'][t['name']] = t['id']

        # Statuses
        if 'product.status' in self.env:
            for s in self.env['product.status'].search_read([], ['id', 'name']):
                cache['statuses'][s['name'].upper()] = s['id']

        # Master Data Config
        MODELS = [
            ('brands', 'product.brand', 'code'),
            ('brands', 'product.brand', 'name'), # Fallback to name
            ('countries', 'product.country', 'code'),
            ('warranties', 'product.warranty', 'code'),
            ('groups', 'product.group', 'cid'),
            ('groups', 'product.group', 'name'),
            ('designs', 'product.design', 'name'),
            ('materials', 'product.material', 'name'),
            ('uvs', 'product.uv', 'cid'),
            ('coatings', 'product.coating', 'cid'),
            ('colors', 'product.cl', 'cid'),
            ('lens_indexes', 'product.lens.index', 'cid'),
            ('frames', 'product.frame', 'cid'),
            ('frame_types', 'product.frame.type', 'cid'),
            ('shapes', 'product.shape', 'cid'),
            ('ves', 'product.ve', 'cid'),
            ('temples', 'product.temple', 'cid'),
        ]
        # Chuẩn bị cache cho power, design, material
        cache['lens_powers'] = {'sph': {}, 'cyl': {}}
        if 'product.lens.power' in self.env:
            for r in self.env['product.lens.power'].search_read([], ['id', 'value', 'type']):
                t = r['type']
                v = float(r['value'])
                cache['lens_powers'][t][v] = r['id']
        cache['lens_designs'] = {}
        if 'product.lens.design' in self.env:
            for r in self.env['product.lens.design'].search_read([], ['id', 'name']):
                cache['lens_designs'][r['name'].strip().lower()] = r['id']
        cache['lens_materials'] = {}
        if 'product.lens.material' in self.env:
            for r in self.env['product.lens.material'].search_read([], ['id', 'name']):
                cache['lens_materials'][r['name'].strip().lower()] = r['id']

        for key, model, _ in MODELS:
            if key not in cache: cache[key] = {}

        for key, model, field in MODELS:
            if model in self.env:
                for r in self.env[model].search_read([], ['id', field]):
                    val = r.get(field)
                    if val: cache[key][val.upper()] = r['id']
                    if model == 'product.group' and key == 'groups':
                        cache['groups_by_id'][r['id']] = r['id']

        # ─── Cache cho Variant Lens (thay thế product.lens) ─────────────────────
        # Cache tên attribute (chữ thường) → attribute.id
        # Ví dụ: {'sph': 1, 'cyl': 2, 'vật liệu': 3, 'thiết kế': 4}
        cache['attr_ids'] = {}
        for a in self.env['product.attribute'].search_read([], ['id', 'name']):
            cache['attr_ids'][a['name'].strip().lower()] = a['id']

        # Cache (attr_id, tên_lower) → attribute_value.id
        # Ví dụ: {(1, '-1.00'): 101, (1, '-2.00'): 102, (2, '-0.50'): 201}
        cache['attr_val_ids'] = {}
        for v in self.env['product.attribute.value'].search_read([], ['id', 'attribute_id', 'name']):
            key = (v['attribute_id'][0], v['name'].strip().lower())
            cache['attr_val_ids'][key] = v['id']

        # Cache (tmpl_id, attr_id) → {'id': line_id, 'value_ids': [val_id,...]}
        # Dùng để biết attribute line nào đã tồn tại trên template nào
        cache['attr_lines'] = {}
        for l in self.env['product.template.attribute.line'].search_read(
            [], ['id', 'product_tmpl_id', 'attribute_id', 'value_ids']
        ):
            key = (l['product_tmpl_id'][0], l['attribute_id'][0])
            cache['attr_lines'][key] = {'id': l['id'], 'value_ids': list(l['value_ids'])}

        # Child Records (giữ lại opt, bỏ lens vì đã dùng variant)
        if 'product.opt' in self.env:
            cache['opt_records'] = {o['product_tmpl_id'][0]: o['id'] for o in self.env['product.opt'].search_read([], ['id', 'product_tmpl_id']) if o.get('product_tmpl_id')}

        return cache

    def _get_val(self, item, key, subkey='cid'):
        return (item.get(key) or {}).get(subkey)

    def _get_id(self, cache, key, val):
        return cache.get(key, {}).get(val.upper(), False) if val else False

    def _get_or_create(self, cache, cache_key, model_name, dto):
        if not dto: return False
        cid = dto.get('cid')
        name = dto.get('name')
        if not cid: return False
        
        # Check cache
        cached_id = cache.get(cache_key, {}).get(cid.upper())
        if cached_id: return cached_id
        
        # Check name fallback in cache (for brands)
        if name and name.upper() in cache.get(cache_key, {}):
            return cache[cache_key][name.upper()]
            
        # Create
        try:
            vals = {'name': name or cid, 'code': cid}
           
            
            rec = self.env[model_name].create(vals)
            new_id = rec.id
            if cid: cache[cache_key][cid.upper()] = new_id
            return new_id
        except Exception as e:
            _logger.error(f"Failed to create {model_name} for {cid}: {e}")
            return False

    def _prepare_base_vals(self, item, cache, product_type):
        dto = item.get('productdto') or {}
        cid = (dto.get('cid') or '').strip()
        if not cid: raise ValueError("Missing CID")
        
        # Category Logic with Code (for product code generation)
        grp_dto = dto.get('groupdto') or {}
        grp_type_name = (grp_dto.get('groupTypedto') or {}).get('name', 'Khác')
        
        # Map product type to category code (matches RS format)
        cat_map = {
            'Mắt': ('Lens Products', 'lens', '06'),      # Code 06 for Lens
            'Gọng': ('Optical OPT', 'opt', '27'),        # Code 27 for Opt
            'Khác': ('Accessories', 'accessory', '20')   # Code 20 for Accessory
        }
        main_cat, _, main_code = cat_map.get(grp_type_name, ('Accessories', 'accessory', '20'))
        
        # Get/Create Category
        cat_name = grp_dto.get('name', 'All Products')
        
        # 1. Ensure Parent Category with code
        parent_key = (main_cat, False)
        if parent_key in cache['categories']:
            parent_id = cache['categories'][parent_key]
        else:
            parent = self.env['product.category'].create({
                'name': main_cat,
                'code': main_code  # Set code for parent category
            })
            parent_id = parent.id
            cache['categories'][parent_key] = parent_id
            
        # 2. Ensure Child Category (inherit parent code if not set)
        cat_key = (cat_name, parent_id)
        if cat_key in cache['categories']:
            categ_id = cache['categories'][cat_key]
        else:
            cat = self.env['product.category'].create({
                'name': cat_name,
                'parent_id': parent_id,
                'code': main_code  # Child categories use same code as parent
            })
            categ_id = cat.id
            cache['categories'][cat_key] = categ_id

        # Group Logic
        grp_id = False
        if 'product.group' in self.env:
            g_id = grp_dto.get('id')
            g_cid = (grp_dto.get('cid') or '').strip().upper()
            g_name = (grp_dto.get('name') or '').strip()
            
            if g_id and g_id in cache['groups_by_id']: grp_id = g_id
            elif g_cid and g_cid in cache['groups']: grp_id = cache['groups'][g_cid]
            elif g_name and g_name.upper() in cache['groups']: grp_id = cache['groups'][g_name.upper()]
            elif g_name:
                # Create Group
                g_type_id = False
                if 'product.group.type' in self.env:
                    gt = self.env['product.group.type'].search([('name', '=', grp_type_name)], limit=1)
                    if not gt: gt = self.env['product.group.type'].create({'name': grp_type_name})
                    g_type_id = gt.id
                
                ng = self.env['product.group'].create({'name': g_name, 'cid': g_cid or '', 'group_type_id': g_type_id, 'product_type': product_type})
                grp_id = ng.id
                if g_cid: cache['groups'][g_cid] = grp_id
                cache['groups'][g_name.upper()] = grp_id
                cache['groups_by_id'][grp_id] = grp_id

        # Supplier Logic - Using seller_ids (Odoo standard)
        seller_vals = []
        s_dto = dto.get('supplierdto') or {}
        s_details = s_dto.get('supplierDetailDTOS', [])
        if s_details:
            s_det = s_details[0]
            s_cid, s_name = s_det.get('cid'), s_det.get('name')
            if s_cid and s_name:
                sup_id = False
                if s_cid.upper() in cache['suppliers']:
                     sup_id = cache['suppliers'][s_cid.upper()]
                else:
                    sup = self.env['res.partner'].create({
                        'name': s_name, 'ref': s_cid, 'is_company': True, 'supplier_rank': 1,
                        'phone': s_det.get('phone', ''), 'email': s_det.get('mail', ''), 'street': s_det.get('address', '')
                    })
                    sup_id = sup.id
                    cache['suppliers'][s_cid.upper()] = sup_id
                
                # Prepare seller_ids values (will be added to product)
                if sup_id:
                    seller_vals.append((0, 0, {
                        'partner_id': sup_id,
                        'price': float(dto.get('orPrice') or 0),  # Supplier price
                        'min_qty': 1.0,
                        'delay': 1,
                    }))

        # Tax (Purchase tax for suppliers)
        tax_pct = float(dto.get('tax') or 0)
        tax_id = False
        if tax_pct > 0:
            t_name = f"Thuế mua hàng {tax_pct}%"
            if t_name in cache['taxes']:
                tax_id = cache['taxes'][t_name]
            else:
                nt = self.env['account.tax'].create({
                    'name': t_name, 
                    'amount': tax_pct, 
                    'amount_type': 'percent', 
                    'type_tax_use': 'purchase'
                })
                tax_id = nt.id
                cache['taxes'][t_name] = tax_id

        # Status
        status_id = False
        if 'product.status' in self.env:
            status_name = (dto.get('statusProductdto') or {}).get('name', '')
            if status_name:
                status_key = status_name.upper()
                if status_key in cache['statuses']:
                    status_id = cache['statuses'][status_key]
                else:
                    # Create new status if not exists
                    ns = self.env['product.status'].create({'name': status_name})
                    status_id = ns.id
                    cache['statuses'][status_key] = status_id

        # Basic Vals
        vals = {
            'name': dto.get('fullname') or 'Unknown',
            'default_code': cid,
            'type': 'consu',
            'categ_id': categ_id,
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'uom_po_id': self.env.ref('uom.product_uom_unit').id,
            'list_price': float(dto.get('rtPrice') or 0),
            'standard_price': float(dto.get('orPrice') or 0),
            'supplier_taxes_id': [(6, 0, [tax_id])] if tax_id else False,
            'seller_ids': seller_vals if seller_vals else False,
            'product_type': product_type,
            'brand_id': self._get_or_create(cache, 'brands', 'product.brand', dto.get('tmdto')),
            'country_id': self._get_or_create(cache, 'countries', 'product.country', dto.get('codto')),
            'warranty_id': self._get_or_create(cache, 'warranties', 'product.warranty', dto.get('warrantydto')),
            'group_id': grp_id,
            # Custom Fields (prefixed with x_)
            'x_eng_name': dto.get('engName', ''),
            'x_trade_name': dto.get('tradeName', ''),
            'description': dto.get('note', ''),
            'x_uses': dto.get('uses', ''),
            'x_guide': dto.get('guide', ''),
            'x_warning': dto.get('warning', ''),
            'x_preserve': dto.get('preserve', ''),
            'x_cid_ncc': dto.get('cidNcc', ''),
            'x_accessory_total': int(dto.get('accessoryTotal') or 0),
            'status_product_id': status_id,
            'x_currency_zone_code': (dto.get('currencyZoneDTO') or {}).get('cid', ''),
            'x_currency_zone_value': float((dto.get('currencyZoneDTO') or {}).get('value') or 0),
            'x_ws_price': float(dto.get('wsPrice') or 0),
            'x_or_price': float(dto.get('orPrice') or 0),
            'x_group_type_name': grp_type_name,
        }
        return vals, cache['products'].get(cid)

    # ════════════════════════════════════════════════════════════════
    # VARIANT MANAGEMENT – Quản lý biến thể product.product cho Lens
    # Thay thế mô hình product.lens cũ để hỗ trợ tồn kho từng SKU
    # ════════════════════════════════════════════════════════════════

    def _get_or_create_attribute(self, cache, attr_name):
        """
        Lấy hoặc tạo product.attribute theo tên.
        Dùng cache['attr_ids'] để tránh query DB lặp lại.
        Ví dụ: 'SPH', 'CYL', 'Vật liệu', 'Thiết kế'
        """
        key = attr_name.strip().lower()
        if key in cache['attr_ids']:
            return cache['attr_ids'][key]

        # Chưa có trong cache → tạo mới
        attr = self.env['product.attribute'].create({
            'name': attr_name,
            # 'always': Odoo tự tạo variant cho mỗi tổ hợp attribute value
            'create_variant': 'always',
        })
        cache['attr_ids'][key] = attr.id
        _logger.info(f"🏷️ Tạo attribute mới: '{attr_name}' (id={attr.id})")
        return attr.id

    def _get_or_create_attr_value(self, cache, attr_id, value_name):
        """
        Lấy hoặc tạo product.attribute.value theo (attr_id, value_name).
        Dùng cache['attr_val_ids'] để tránh query DB lặp lại.
        Ví dụ: attr 'SPH' + value '-1.00', '-2.00'...
        """
        key = (attr_id, value_name.strip().lower())
        if key in cache['attr_val_ids']:
            return cache['attr_val_ids'][key]

        # Chưa có → tạo mới cho attribute này
        val = self.env['product.attribute.value'].create({
            'attribute_id': attr_id,
            'name': value_name,
        })
        cache['attr_val_ids'][key] = val.id
        return val.id

    def _ensure_attr_line(self, cache, tmpl_id, attr_id, value_id):
        """
        Đảm bảo product.template.attribute.line tồn tại trên template và
        chứa value_id cần thiết.
        - Nếu line chưa có → tạo mới với value đó
        - Nếu line đã có nhưng value chưa trong danh sách → append thêm
        Khi thêm value mới, Odoo tự động tạo thêm variant tương ứng.
        """
        key = (tmpl_id, attr_id)
        if key in cache['attr_lines']:
            line_info = cache['attr_lines'][key]
            if value_id not in line_info['value_ids']:
                # Append value vào line hiện có (Odoo tự tạo variant mới)
                self.env['product.template.attribute.line'].browse(line_info['id']).write(
                    {'value_ids': [(4, value_id)]}
                )
                line_info['value_ids'].append(value_id)
        else:
            # Tạo attribute line mới cho template này
            line = self.env['product.template.attribute.line'].create({
                'product_tmpl_id': tmpl_id,
                'attribute_id': attr_id,
                'value_ids': [(4, value_id)],
            })
            cache['attr_lines'][key] = {'id': line.id, 'value_ids': [value_id]}

    def _find_variant_by_attrs(self, tmpl_id, attr_value_ids):
        """
        Tìm product.product variant khớp đúng với tập attribute value IDs.
        So sánh bằng set để không phụ thuộc vào thứ tự.
        Trả về variant.id nếu tìm thấy, False nếu không có.
        """
        target = set(attr_value_ids)
        template = self.env['product.template'].browse(tmpl_id)
        for variant in template.product_variant_ids:
            # Lấy tập attribute value IDs thực tế của variant này
            variant_val_ids = set(
                variant.product_template_attribute_value_ids
                .mapped('product_attribute_value_id').ids
            )
            if variant_val_ids == target:
                return variant.id
        return False

    def _sync_lens_variant(self, tmpl_id, item, cache):
        """
        Đồng bộ 1 bản ghi lens từ API thành product.product variant.
        Thay thế logic tạo product.lens để hỗ trợ tồn kho riêng từng SKU.

        Các attribute chính tạo nên biến thể:
          - SPH   : Công suất cầu (ví dụ: -1.00, +2.50, 0.00)
          - CYL   : Công suất trụ (ví dụ: -0.50, -1.00, 0.00)
          - Vật liệu : Chất liệu tròng (ví dụ: CR39, Polycarbonate, Trivex)
          - Thiết kế : Kiểu tròng (ví dụ: Single Vision, Progressive)

        Trả về variant_id (product.product.id) tương ứng.
        """
        # ─── Thu thập các attribute value từ API ─────────────────────────
        attr_map = {}  # {tên_attribute: giá_trị}

        # SPH – Công suất cầu
        sph_val = item.get('sph')
        if sph_val is not None and str(sph_val).strip():
            attr_map['SPH'] = str(sph_val).strip()

        # CYL – Công suất trụ
        cyl_val = item.get('cyl')
        if cyl_val is not None and str(cyl_val).strip():
            attr_map['CYL'] = str(cyl_val).strip()

        # Vật liệu tròng kính
        material_val = (item.get('material') or '').strip()
        if material_val:
            attr_map['Vật liệu'] = material_val

        # Thiết kế tròng (Single Vision, Progressive, Bifocal...)
        design_val = (item.get('design') or '').strip()
        if design_val:
            attr_map['Thiết kế'] = design_val

        # Nếu không có attribute nào thì trả về variant mặc định của template
        if not attr_map:
            template = self.env['product.template'].browse(tmpl_id)
            return template.product_variant_id.id

        # ─── Tạo/lấy attribute và value, gán vào template ────────────────
        attr_value_ids = []
        for attr_name, value_name in attr_map.items():
            attr_id = self._get_or_create_attribute(cache, attr_name)
            value_id = self._get_or_create_attr_value(cache, attr_id, value_name)
            self._ensure_attr_line(cache, tmpl_id, attr_id, value_id)
            attr_value_ids.append(value_id)

        # ─── Tìm variant khớp ─────────────────────────────────────────────
        # Sau khi attribute lines được cập nhật, Odoo tự tạo variant mới.
        # Ta tìm lại variant có đúng tập attribute values.
        variant_id = self._find_variant_by_attrs(tmpl_id, attr_value_ids)
        if not variant_id:
            _logger.warning(
                f"⚠️ Không tìm thấy variant cho template {tmpl_id} "
                f"với {attr_map}. Dùng variant mặc định."
            )
            template = self.env['product.template'].browse(tmpl_id)
            variant_id = template.product_variant_id.id

        return variant_id

    def _prepare_lens_vals(self, item, cache):
        # Xử lý SPH/CYL: API trả về string, cần ép kiểu float rồi tra cache
        def get_power_id(val, t):
            try:
                fval = float(val)
            except Exception:
                return False
            return cache['lens_powers'][t].get(fval)

        sph_val = item.get('sph')
        cyl_val = item.get('cyl')
        design_name = (item.get('design') or '').strip().lower()
        material_name = (item.get('material') or '').strip().lower()

        v = {
            'sph_id': get_power_id(sph_val, 'sph'),
            'cyl_id': get_power_id(cyl_val, 'cyl'),
            'design_id': cache['lens_designs'].get(design_name),
            'material_id': cache['lens_materials'].get(material_name),
            'len_add': item.get('lensAdd', ''),
            'diameter': item.get('diameter', ''),
            'corridor': item.get('corridor', ''),
            'abbe': item.get('abbe', ''),
            'polarized': item.get('polarized', ''),
            'prism': item.get('prism', ''),
            'base_curve': item.get('base', ''),
            'axis': item.get('axis', ''),
            'prism_base': item.get('prismBase', ''),
            'color_int': item.get('colorInt', ''),
            'mir_coating': item.get('mirCoating', ''),
        }
        # Coating/Feature xử lý sau nếu cần
        return v

    def _prepare_opt_vals(self, item, cache):
        v = {
            'season': item.get('season', ''), 'model': item.get('model', ''), 'serial': item.get('serial', ''),
            'oem_ncc': item.get('oemNcc', ''), 'sku': item.get('sku', ''), 'color': item.get('color', ''),
            'gender': str(item.get('gender', '')) if item.get('gender') else False,
            'temple_width': int(item.get('templeWidth') or 0), 'lens_width': int(item.get('lensWidth') or 0),
            'lens_span': int(item.get('lensSpan') or 0), 'lens_height': int(item.get('lensHeight') or 0),
            'bridge_width': int(item.get('bridgeWidth') or 0),
            'color_lens_id': self._get_id(cache, 'colors', self._get_val(item, 'colorLensdto')),
            'frame_id': self._get_id(cache, 'frames', self._get_val(item, 'framedto')),
            'frame_type_id': self._get_id(cache, 'frame_types', self._get_val(item, 'frameTypedto')),
            'shape_id': self._get_id(cache, 'shapes', self._get_val(item, 'shapedto')),
            've_id': self._get_id(cache, 'ves', self._get_val(item, 'vedto')),
            'temple_id': self._get_id(cache, 'temples', self._get_val(item, 'templedto')),
            'material_ve_id': self._get_id(cache, 'materials', self._get_val(item, 'materialVedto')),
            'material_temple_tip_id': self._get_id(cache, 'materials', self._get_val(item, 'materialTempleTipdto')),
            'material_lens_id': self._get_id(cache, 'materials', self._get_val(item, 'materialLensdto')),
        }
        return v

    def _process_batch(self, items, cache, product_type, child_model=None):
        """
        Xử lý batch create/update sản phẩm từ API.
        - Với 'lens': dùng _sync_lens_variant để tạo product.product variant
          (có tồn kho riêng từng SKU). KHÔNG dùng product.lens nữa.
        - Với 'opt': vẫn dùng child model product.opt như cũ.
        - Với loại khác: chỉ tạo/update product.template.
        """
        total = len(items)
        success = failed = 0
        to_create, to_update = [], []
        # Lưu item gốc theo index để xử lý variant sau khi template được tạo
        items_to_create = []   # list of (idx, item) cho lens create
        items_to_update = []   # list of (tmpl_id, item) cho lens update

        # child model chỉ dùng cho 'opt', không dùng cho 'lens' nữa
        has_child = (product_type != 'lens') and child_model and child_model in self.env
        child_vals_map = {}   # tmpl_id → child_vals (chỉ dùng cho opt)
        new_child_data = []   # [(idx, child_vals)] cho opt

        _logger.info(f"🔄 Processing {total} {product_type} items...")

        # ─── Bước 1: Chuẩn bị dữ liệu ────────────────────────────────────
        for idx, item in enumerate(items):
            try:
                vals, pid = self._prepare_base_vals(item, cache, product_type)

                if product_type == 'lens':
                    # Lens: không dùng child_vals, lưu item lại để sync variant sau
                    if pid:
                        to_update.append((pid, vals))
                        items_to_update.append((pid, item))
                    else:
                        to_create.append(vals)
                        items_to_create.append((idx, item))
                else:
                    # Opt/Accessory: xử lý child model như cũ
                    c_vals = {}
                    if has_child and product_type == 'opt':
                        c_vals = self._prepare_opt_vals(item, cache)
                    if pid:
                        to_update.append((pid, vals))
                        if has_child:
                            child_vals_map[pid] = c_vals
                    else:
                        to_create.append(vals)
                        if has_child:
                            new_child_data.append((idx, c_vals))
            except Exception as e:
                failed += 1
                _logger.error(f"Prepare error [{product_type}]: {e}")

        # ─── Bước 2: Batch Create ─────────────────────────────────────────
        if to_create:
            batch_size = 100
            for i in range(0, len(to_create), batch_size):
                b_vals = to_create[i:i + batch_size]
                # Lấy items tương ứng cho đoạn batch này (dùng cho lens variant)
                b_items = items_to_create[i:i + batch_size] if product_type == 'lens' else []
                b_child = new_child_data[i:i + batch_size] if has_child else []
                try:
                    with self.env.cr.savepoint():
                        recs = self.env['product.template'].with_context(
                            tracking_disable=True
                        ).create(b_vals)

                        for j, rec in enumerate(recs):
                            cache['products'][rec.default_code] = rec.id

                            if product_type == 'lens':
                                # Tạo variant product.product dựa vào specs của item
                                _, orig_item = b_items[j]
                                try:
                                    self._sync_lens_variant(rec.id, orig_item, cache)
                                except Exception as ve:
                                    _logger.error(
                                        f"❌ Lỗi tạo variant lens cho template "
                                        f"{rec.default_code}: {ve}"
                                    )
                            elif has_child and b_child:
                                # Opt: tạo child record như cũ
                                _, cv = b_child[j]
                                cv['product_tmpl_id'] = rec.id
                                self.env[child_model].create(cv)

                        success += len(recs)
                except Exception as e:
                    failed += len(b_vals)
                    _logger.error(f"Batch Create Error [{product_type}]: {e}")

        # ─── Bước 3: Batch Update ─────────────────────────────────────────
        # Ghép (tmpl_id, vals) với item gốc để gọi _sync_lens_variant
        update_lens_map = {pid: item for pid, item in items_to_update}

        for pid, vals in to_update:
            try:
                with self.env.cr.savepoint():
                    self.env['product.template'].browse(pid).with_context(
                        tracking_disable=True
                    ).write(vals)

                    if product_type == 'lens':
                        # Cập nhật/tạo variant cho template đã tồn tại
                        orig_item = update_lens_map.get(pid, {})
                        try:
                            self._sync_lens_variant(pid, orig_item, cache)
                        except Exception as ve:
                            _logger.error(
                                f"❌ Lỗi cập nhật variant lens cho template "
                                f"{pid}: {ve}"
                            )
                    elif has_child and pid in child_vals_map:
                        # Opt: cập nhật child record như cũ
                        c_vals = child_vals_map[pid]
                        cmap = cache.get('opt_records', {})
                        if pid in cmap:
                            self.env[child_model].browse(cmap[pid]).write(c_vals)
                        else:
                            c_vals['product_tmpl_id'] = pid
                            cid = self.env[child_model].create(c_vals).id
                            cmap[pid] = cid

                    success += 1
            except Exception as e:
                failed += 1
                _logger.error(f"Update Error [{product_type}] tmpl_id={pid}: {e}")

        return success, failed


    def sync_products_from_springboot(self):
        # If called from cron/server action, self might be empty
        rec = self
        if not rec:
            rec = self.search([], limit=1, order='last_sync_date desc')
            if not rec:
                rec = self.create({'name': 'Đồng bộ tự động hàng ngày'})
        return rec._run_sync()

    def sync_products_limited(self, limit=200):
        return self._run_sync(limit)

    def _run_sync(self, limit=None):
        self.ensure_one()
        try:
            self.write({'sync_status': 'in_progress', 'sync_log': 'Đang đồng bộ...', 'last_sync_date': fields.Datetime.now()})
            self.env.cr.commit()
            
            token = self._get_access_token()
            cache = self._preload_all_data()
            cfg = self._get_api_config()
            stats = {}
            
            # Lens – dùng _sync_lens_variant (không cần child_model product.lens nữa)
            # Mỗi bản ghi lens từ API → 1 product.product variant có tồn kho riêng
            items = self._fetch_all_items(cfg['lens_endpoint'], token, 'Lens', limit)
            s, f = self._process_batch(items, cache, 'lens')  # Không truyền child_model
            stats['lens'] = s
            stats['failed'] = f
            self.env.cr.commit()
            
            # Opt
            items = self._fetch_all_items(cfg['opts_endpoint'], token, 'Optical', limit)
            s, f = self._process_batch(items, cache, 'opt', 'product.opt')
            stats['opt'] = s
            stats['failed'] += f
            self.env.cr.commit()

            # Access
            items = self._fetch_all_items(cfg['types_endpoint'], token, 'Types', limit)
            s, f = self._process_batch(items, cache, 'accessory')
            stats['acc'] = s
            stats['failed'] += f
            self.env.cr.commit()
            
            total = stats['lens'] + stats['opt'] + stats['acc']
            msg = f"Đã đồng bộ {total} (Mắt:{stats['lens']}, Gọng:{stats['opt']}, Khác:{stats['acc']}). Lỗi: {stats['failed']}"
            self.write({'sync_status': 'success' if stats['failed'] == 0 else 'success', 'sync_log': msg, 
                       'total_synced': total, 'total_failed': stats['failed'], 
                       'lens_count': stats['lens'], 'opts_count': stats['opt'], 'other_count': stats['acc']})
            
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Đồng bộ hoàn tất', 'message': msg, 'type': 'success'}}

        except Exception as e:
            self.env.cr.rollback()
            self.write({'sync_status': 'error', 'sync_log': str(e)})
            self.env.cr.commit()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Đồng bộ thất bại', 'message': str(e), 'type': 'danger'}}

    def test_api_connection(self):
        try:
            token = self._get_access_token()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Kết nối thành công', 'message': 'Đã lấy được token.', 'type': 'success'}}
        except Exception as e:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Kết nối thất bại', 'message': str(e), 'type': 'danger'}}
