# -*- coding: utf-8 -*-
import logging
import os
import time
import random
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
            'login_timeout': int(os.getenv('LOGIN_TIMEOUT', '300')),
            'api_timeout': int(os.getenv('API_TIMEOUT', '9999')),
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

    def _make_session(self):
        """Tạo mới requests.Session (không cache trên self vì Odoo ORM không cho phép)."""
        from requests.adapters import HTTPAdapter
        session = requests.Session()
        session.mount('https://', HTTPAdapter(max_retries=0))
        session.mount('http://', HTTPAdapter(max_retries=0))
        return session

    def _fetch_paged_api(self, endpoint, token, page=0, size=100, max_retries=5, session=None):
        config = self._get_api_config()
        url = f"{config['base_url']}{endpoint}?page={page}&size={size}"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        for attempt in range(1, max_retries + 1):
            # Tạo session mới nếu chưa có hoặc sau khi retry
            _session = session if (session and attempt == 1) else self._make_session()
            try:
                response = _session.get(
                    url, headers=headers,
                    verify=config['ssl_verify'],
                    timeout=config['api_timeout']
                )
                response.raise_for_status()
                return response.json()
            except (requests.exceptions.ConnectTimeout,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectionError) as e:
                if attempt == max_retries:
                    raise UserError(_(f"API request failed after {max_retries} retries: {str(e)}"))
                wait = min(2 ** attempt + random.uniform(0, 2), 60)  # cap 60s
                _logger.warning(
                    f"⚠️ Timeout/Connection error trang {page} (lần {attempt}/{max_retries}). "
                    f"Thử lại sau {wait:.1f}s... Lỗi: {e}"
                )
                time.sleep(wait)
            except Exception as e:
                raise UserError(_(f"API request failed: {str(e)}"))

    def _fetch_all_items(self, endpoint, token, label, limit=None, page_delay=0.3):
        """Lấy toàn bộ dữ liệu phân trang với retry & delay giữa các trang.
        
        Args:
            page_delay: Giây tạm nghỉ giữa mỗi trang để tránh server quá tải (mặc định 0.3s).
        """
        items = []
        page = 0
        total_elements = 0
        config = self._get_api_config()
        
        _logger.info(f"🔍 Bắt đầu lấy dữ liệu {label} từ: {config['base_url']}{endpoint}")

        # Tạo session một lần duy nhất cho toàn bộ quá trình phân trang
        session = self._make_session()

        while True:
            res = self._fetch_paged_api(endpoint, token, page, 100, session=session)
            
            if page == 0:
                debug_res = {k: v for k, v in res.items() if k != 'content'}
                _logger.info(f"🔍 Metadata API {label} (Trang 0): {debug_res}")
            
            content = res.get('content', [])
            if not content:
                break
            items.extend(content)
            
            total_elements = res.get('totalElements', 0)
            total_pages = res.get('totalPages', 1)
            
            _logger.info(
                f"📦 {label}: Trang {page + 1}/{total_pages} | "
                f"Lấy được {len(content)} bản ghi | Tổng: {len(items)}/{total_elements}"
            )

            # Cập nhật sync_log định kỳ (mỗi 10 trang) để UI hiển thị tiến độ
            if page % 10 == 0 and hasattr(self, 'id') and self.id:
                try:
                    self.write({'sync_log': f"Đang tải {label}: trang {page + 1}/{total_pages} ({len(items)}/{total_elements} bản ghi)..."})
                    self.env.cr.commit()
                except Exception:
                    pass
            
            if limit and len(items) >= limit:
                return items[:limit]
            
            page += 1
            if page >= total_pages:
                break

            # Nghỉ một chút giữa các trang để tránh connection timeout do quá tải
            if page_delay > 0:
                time.sleep(page_delay)
            
        if total_elements > len(items) and not limit:
            _logger.warning(
                f"⚠️ API báo có {total_elements} bản ghi {label} nhưng chỉ lấy được {len(items)}."
            )
            
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

        # Child Records (giữ lại opt)
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

        # ─── Lens specs (Hướng B: field trực tiếp trên template) ──────────
        if product_type == 'lens':
            def get_lens_power(field_key, power_type):
                try:
                    return cache['lens_powers'][power_type].get(float(item.get(field_key)))
                except (TypeError, ValueError):
                    return False

            design_name = (item.get('design') or '').strip().upper()
            material_name = (item.get('material') or '').strip().lower()

            # Coatings – API trả về list DTOs (e.g. [{cid: 'ARC', ...}, ...])
            coating_ids = []
            for c in (item.get('coatingdtos') or []):
                c_cid = (c.get('cid') or '').upper()
                cid_val = cache.get('coatings', {}).get(c_cid)
                if cid_val:
                    coating_ids.append(cid_val)

            vals.update({
                'lens_sph_id': get_lens_power('sph', 'sph'),
                'lens_cyl_id': get_lens_power('cyl', 'cyl'),
                'lens_add': float(item.get('lensAdd') or 0),
                'lens_base_curve': float(item.get('base') or 0),
                'lens_diameter': int(item.get('diameter') or 0),
                'lens_prism': (item.get('prism') or ''),
                'lens_design1_id': cache.get('designs', {}).get(design_name) if design_name else False,
                'lens_material_id': cache['lens_materials'].get(material_name) if material_name else False,
                'lens_index_id': self._get_id(cache, 'lens_indexes', self._get_val(item, 'indexdto')),
                'lens_uv_id': self._get_id(cache, 'uvs', self._get_val(item, 'uvdto')),
                'lens_color_int': (item.get('colorInt') or ''),
                'lens_mir_coating': (item.get('mirCoating') or ''),
                'lens_coating_ids': [(6, 0, coating_ids)] if coating_ids else False,
            })

        # ─── Opt specs (Hướng B: field trực tiếp trên template) ──────────────────────
        if product_type == 'opt':
            vals.update(self._prepare_opt_vals(item, cache))

        return vals, cache['products'].get(cid)

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

        def safe_int(val, default=0):
            try: return int(val) if val not in (None, '', False) else default
            except Exception: return default

        def safe_float(val, default=0.0):
            try: return float(val) if val not in (None, '', False) else default
            except Exception: return default

        v = {
            'sph_id': get_power_id(sph_val, 'sph'),
            'cyl_id': get_power_id(cyl_val, 'cyl'),
            'design_id': cache['lens_designs'].get(design_name),
            'material_id': cache['lens_materials'].get(material_name),
            'lens_add': safe_float(item.get('lensAdd')),   # FIX: len_add → lens_add
            'diameter': safe_int(item.get('diameter')),     # Integer field
            'base_curve': safe_float(item.get('base')),
            'axis': safe_int(item.get('axis')),
            'corridor': item.get('corridor') or '',
            'abbe': item.get('abbe') or '',
            'prism': item.get('prism') or '',
            'prism_base': item.get('prismBase') or '',
        }
        # Coating/Feature xử lý sau nếu cần
        return v

    def _prepare_opt_vals(self, item, cache):
        """Map opt specs từ API trực tiếp vào opt_* fields trên product.template."""
        return {
            'opt_season': item.get('season', ''),
            'opt_model': item.get('model', ''),
            'opt_serial': item.get('serial', ''),
            'opt_oem_ncc': item.get('oemNcc', ''),
            'opt_sku': item.get('sku', ''),
            'opt_color': item.get('color', ''),
            'opt_gender': str(item.get('gender', '')) if item.get('gender') else False,
            'opt_temple_width': int(item.get('templeWidth') or 0),
            'opt_lens_width': int(item.get('lensWidth') or 0),
            'opt_lens_span': int(item.get('lensSpan') or 0),
            'opt_lens_height': int(item.get('lensHeight') or 0),
            'opt_bridge_width': int(item.get('bridgeWidth') or 0),
            'opt_color_lens_id': self._get_id(cache, 'colors', self._get_val(item, 'colorLensdto')),
            'opt_frame_id': self._get_id(cache, 'frames', self._get_val(item, 'framedto')),
            'opt_frame_type_id': self._get_id(cache, 'frame_types', self._get_val(item, 'frameTypedto')),
            'opt_shape_id': self._get_id(cache, 'shapes', self._get_val(item, 'shapedto')),
            'opt_ve_id': self._get_id(cache, 'ves', self._get_val(item, 'vedto')),
            'opt_temple_id': self._get_id(cache, 'temples', self._get_val(item, 'templedto')),
            'opt_material_ve_id': self._get_id(cache, 'materials', self._get_val(item, 'materialVedto')),
            'opt_material_temple_tip_id': self._get_id(cache, 'materials', self._get_val(item, 'materialTempleTipdto')),
            'opt_material_lens_id': self._get_id(cache, 'materials', self._get_val(item, 'materialLensdto')),
        }

    def _process_batch(self, items, cache, product_type, child_model=None):
        """
        Xử lý batch create/update sản phẩm từ API.
        - Lens và Opt: specs đã được map trực tiếp vào template (Hướng B).
        - Accessory và các loại khác: chỉ tạo/update product.template.
        """
        total = len(items)
        success = failed = 0
        to_create, to_update = [], []

        has_child = False  # Hướng B: không còn dùng child model cho lens hay opt
        child_vals_map = {}    # tmpl_id → child_vals (cho opt)
        new_child_data = []    # [(idx, child_vals)] cho opt create

        _logger.info(f"🔄 Processing {total} {product_type} items...")

        # ─── Bước 1: Chuẩn bị dữ liệu ────────────────────────────────────
        for idx, item in enumerate(items):
            try:
                vals, pid = self._prepare_base_vals(item, cache, product_type)
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
                b_child = new_child_data[i:i + batch_size] if has_child else []
                b_child_refs = b_child
                try:
                    with self.env.cr.savepoint():
                        recs = self.env['product.template'].with_context(
                            tracking_disable=True
                        ).create(b_vals)

                        for j, rec in enumerate(recs):
                            cache['products'][rec.default_code] = rec.id
                        success += len(recs)
                except Exception as e:
                    failed += len(b_vals)
                    _logger.error(f"Batch Create Error [{product_type}]: {e}")
                    continue

                # Tạo child records riêng lẻ (savepoint độc lập)
                if has_child and b_child_refs:
                    for j, rec in enumerate(recs):
                        if j >= len(b_child_refs):
                            break
                        _, cv = b_child_refs[j]
                        if not cv:
                            _logger.warning(f"⚠️ Bỏ qua child record rỗng cho product {rec.id}")
                            continue
                        cv['product_tmpl_id'] = rec.id
                        try:
                            with self.env.cr.savepoint():
                                self.env[child_model].create(cv)
                        except Exception as e:
                            _logger.error(f"Child Create Error product {rec.id}: {e}")

        # ─── Bước 3: Batch Update ─────────────────────────────────────────
        for pid, vals in to_update:
            try:
                with self.env.cr.savepoint():
                    self.env['product.template'].browse(pid).with_context(
                        tracking_disable=True
                    ).write(vals)

                    if has_child and pid in child_vals_map:
                        c_vals = child_vals_map[pid]
                        cmap = cache.get('opt_records', {})
                        if pid in cmap:
                            self.env[child_model].browse(cmap[pid]).write(c_vals)
                        else:
                            c_vals['product_tmpl_id'] = pid
                            new_id = self.env[child_model].create(c_vals).id
                            cmap[pid] = new_id

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
            
            # Lens – specs đã map trực tiếp vào template (Hướng B)
            # Mỗi bản ghi lens từ API → 1 product.template + 1 default variant
            items = self._fetch_all_items(cfg['lens_endpoint'], token, 'Lens', limit)
            s, f = self._process_batch(items, cache, 'lens')  # Không truyền child_model
            stats['lens'] = s
            stats['failed'] = f
            self.env.cr.commit()
            
            # Opt – specs đã map trực tiếp vào template (Hướng B)
            items = self._fetch_all_items(cfg['opts_endpoint'], token, 'Optical', limit)
            s, f = self._process_batch(items, cache, 'opt')  # Không dùng child_model
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
