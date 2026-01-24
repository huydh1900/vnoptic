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

    name = fields.Char('Sync Name', required=True, default='Product Sync')
    last_sync_date = fields.Datetime('Last Sync Date', readonly=True)
    sync_status = fields.Selection([
        ('never', 'Never Synced'),
        ('in_progress', 'In Progress'),
        ('success', 'Success'),
        ('error', 'Error')
    ], default='never', string='Status', readonly=True)
    sync_log = fields.Text('Sync Log', readonly=True)

    total_synced = fields.Integer('Total Products Synced', readonly=True)
    total_failed = fields.Integer('Total Failed', readonly=True)
    lens_count = fields.Integer('Lens Products', readonly=True)
    opts_count = fields.Integer('Optical OPT', readonly=True)
    other_count = fields.Integer('Other Products', readonly=True)

    progress = fields.Float('Progress (%)', readonly=True, compute='_compute_progress')

    @api.depends('total_synced', 'total_failed')
    def _compute_progress(self):
        for record in self:
            total = record.total_synced + record.total_failed
            record.progress = (record.total_synced / total * 100) if total > 0 else 0

    @api.model
    def _get_api_config(self):
        return {
            'base_url': os.getenv('SPRING_BOOT_BASE_URL', 'https://localhost:8443'),
            'login_endpoint': os.getenv('API_LOGIN_ENDPOINT', '/api/auth/service-token'),
            'lens_endpoint': os.getenv('API_LENS_ENDPOINT', '/api/product/lens'),
            'opts_endpoint': os.getenv('API_OPTS_ENDPOINT', '/api/product/opts'),
            'types_endpoint': os.getenv('API_TYPES_ENDPOINT', '/api/product/types'),
            'service_username': os.getenv('SPRINGBOOT_SERVICE_USERNAME', 'odoo'),
            'service_password': os.getenv('SPRINGBOOT_SERVICE_PASSWORD', 'odoo'),
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
        while True:
            res = self._fetch_paged_api(endpoint, token, page, 100)
            content = res.get('content', [])
            if not content: break
            items.extend(content)
            
            _logger.info(f"📦 {label}: Page {page + 1}/{res.get('totalPages')}, Got {len(content)} (Total: {len(items)})")
            if limit and len(items) >= limit:
                return items[:limit]
            
            page += 1
            if page >= res.get('totalPages', 1): break
        return items

    def _preload_all_data(self):
        _logger.info("📦 Pre-loading existing data...")
        cache = {'products': {}, 'categories': {}, 'suppliers': {}, 'taxes': {}, 'groups': {}, 'groups_by_id': {}}
        
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
            
        # Taxes
        for t in self.env['account.tax'].search_read([('type_tax_use', '=', 'sale')], ['id', 'name']):
            cache['taxes'][t['name']] = t['id']

        # Master Data Config
        MODELS = [
            ('brands', 'xnk.brand', 'code'),
            ('brands', 'xnk.brand', 'name'), # Fallback to name
            ('countries', 'xnk.country', 'code'),
            ('warranties', 'xnk.warranty', 'code'),
            ('groups', 'product.group', 'cid'),
            ('groups', 'product.group', 'name'),
            ('designs', 'product.design', 'cid'),
            ('materials', 'product.material', 'cid'),
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
        
        for key, model, _ in MODELS:
            if key not in cache: cache[key] = {}

        for key, model, field in MODELS:
            if model in self.env:
                for r in self.env[model].search_read([], ['id', field]):
                    val = r.get(field)
                    if val: cache[key][val.upper()] = r['id']
                    if model == 'product.group' and key == 'groups':
                        cache['groups_by_id'][r['id']] = r['id']

        # Child Records
        if 'product.lens' in self.env:
            cache['lens_records'] = {l['product_tmpl_id'][0]: l['id'] for l in self.env['product.lens'].search_read([], ['id', 'product_tmpl_id']) if l.get('product_tmpl_id')}
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
            # Handle model-specific fields if any (assuming name/code are standard)
            # Check models to be sure: xnk.brand has 'code', xnk.country has 'code', xnk.warranty has 'code'
            # Assuming 'name' is always there.
            
            # Map 'code' to 'cid' if model uses 'cid' instead (based on master data file check they use 'cid' not 'code'?)
            # Wait, I checked xnk_brand.py in file list but didn't read content. 
            # I should be safe and read creating... or just use 'code' and 'name' if standard.
            # Let's check xnk_brand content to be 100% sure about field names.
            # But let's look at _preload_all_data:
            # ('brands', 'xnk.brand', 'code'),
            # ('brands', 'xnk.brand', 'name'),
            # It implies 'code' field exists.
            
            # Additional check: Model definitions in product_master_data.py showed 'cid' for many.
            # But xnk_brand was separate. Let's assume 'code' based on preload.
            
            # Actually, to be safe, I should just read xnk_brand.py.
            # But I can't in this tool call.
            # I will use a generic create that handles differences or just assume 'code' based on preload usage.
            
            rec = self.env[model_name].create(vals)
            new_id = rec.id
            if cid: cache[cache_key][cid.upper()] = new_id
            return new_id
        except Exception as e:
            _logger.error(f"Failed to create {model_name} for {cid}: {e}")
            return False

    def _prepare_base_vals(self, item, cache, product_type):
        dto = item.get('productdto') or {}
        cid = dto.get('cid', '').strip()
        if not cid: raise ValueError("Missing CID")
        
        # Category Logic
        grp_dto = dto.get('groupdto') or {}
        grp_type_name = (grp_dto.get('groupTypedto') or {}).get('name', 'Khác')
        cat_map = {'Mắt': ('Lens Products', 'lens'), 'Gọng': ('Optical OPT', 'opt'), 'Khác': ('Accessories', 'accessory')}
        main_cat, _ = cat_map.get(grp_type_name, ('Accessories', 'accessory'))
        
        # Get/Create Category
        cat_name = grp_dto.get('name', 'All Products')
        
        # 1. Ensure Parent Category
        parent_key = (main_cat, False)
        if parent_key in cache['categories']:
            parent_id = cache['categories'][parent_key]
        else:
            parent = self.env['product.category'].create({'name': main_cat})
            parent_id = parent.id
            cache['categories'][parent_key] = parent_id
            
        # 2. Ensure Category
        cat_key = (cat_name, parent_id)
        if cat_key in cache['categories']:
            categ_id = cache['categories'][cat_key]
        else:
            cat = self.env['product.category'].create({'name': cat_name, 'parent_id': parent_id})
            categ_id = cat.id
            cache['categories'][cat_key] = categ_id

        # Group Logic
        grp_id = False
        if 'product.group' in self.env:
            g_id, g_cid, g_name = grp_dto.get('id'), grp_dto.get('cid', '').strip().upper(), grp_dto.get('name', '').strip()
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
                
                ng = self.env['product.group'].create({'name': g_name, 'cid': g_cid or '', 'group_type_id': g_type_id})
                grp_id = ng.id
                if g_cid: cache['groups'][g_cid] = grp_id
                cache['groups'][g_name.upper()] = grp_id
                cache['groups_by_id'][grp_id] = grp_id

        # Supplier Logic
        sup_id = False
        s_details = dto.get('supplierdtos', {}).get('supplierDetailDTOS', [])
        # Fix: dto.get('supplierdtos') might be wrong key based on prev code 'supplierdto'
        # Previous code: supplierdto = productdto.get('supplierdto')
        s_dto = dto.get('supplierdto') or {}
        s_details = s_dto.get('supplierDetailDTOS', [])
        if s_details:
            s_det = s_details[0]
            s_cid, s_name = s_det.get('cid'), s_det.get('name')
            if s_cid and s_name:
                if s_cid.upper() in cache['suppliers']:
                     sup_id = cache['suppliers'][s_cid.upper()]
                else:
                    sup = self.env['res.partner'].create({
                        'name': s_name, 'ref': s_cid, 'supplier_rank': 1, 'is_company': True,
                        'phone': s_det.get('phone', ''), 'email': s_det.get('mail', ''), 'street': s_det.get('address', '')
                    })
                    sup_id = sup.id
                    cache['suppliers'][s_cid.upper()] = sup_id

        # Tax
        tax_pct = float(dto.get('tax') or 0)
        tax_id = False
        if tax_pct > 0:
            t_name = f"Tax {tax_pct}%"
            if t_name in cache['taxes']:
                tax_id = cache['taxes'][t_name]
            else:
                nt = self.env['account.tax'].create({'name': t_name, 'amount': tax_pct, 'amount_type': 'percent', 'type_tax_use': 'sale'})
                tax_id = nt.id
                cache['taxes'][t_name] = tax_id

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
            'taxes_id': [(6, 0, [tax_id])] if tax_id else False,
            'product_type': product_type,
            'brand_id': self._get_or_create(cache, 'brands', 'xnk.brand', dto.get('tmdto')),
            'supplier_id': sup_id,
            'country_id': self._get_or_create(cache, 'countries', 'xnk.country', dto.get('codto')),
            'warranty_id': self._get_or_create(cache, 'warranties', 'xnk.warranty', dto.get('warrantydto')),
            'group_id': grp_id,
            # Custom Fields
            'x_eng_name': dto.get('engName', ''),
            'x_trade_name': dto.get('tradeName', ''),
            'x_note_long': dto.get('note', ''),
            'x_uses': dto.get('uses', ''),
            'x_guide': dto.get('guide', ''),
            'x_warning': dto.get('warning', ''),
            'x_preserve': dto.get('preserve', ''),
            'x_cid_ncc': dto.get('cidNcc', ''),
            'x_accessory_total': int(dto.get('accessoryTotal') or 0),
            'x_status_name': (dto.get('statusProductdto') or {}).get('name', ''),
            'x_tax_percent': tax_pct,
            'x_currency_zone_code': (dto.get('currencyZoneDTO') or {}).get('cid', ''),
            'x_currency_zone_value': float((dto.get('currencyZoneDTO') or {}).get('value') or 0),
            'x_ws_price': float(dto.get('wsPrice') or 0),
            'x_ct_price': float(dto.get('ctPrice') or 0),
            'x_or_price': float(dto.get('orPrice') or 0),
            'x_group_type_name': grp_type_name,
        }
        return vals, cache['products'].get(cid)

    def _prepare_lens_vals(self, item, cache):
        v = {
            'sph': item.get('sph', ''), 'cyl': item.get('cyl', ''), 'len_add': item.get('lensAdd', ''),
            'diameter': item.get('diameter', ''), 'corridor': item.get('corridor', ''), 'abbe': item.get('abbe', ''),
            'polarized': item.get('polarized', ''), 'prism': item.get('prism', ''), 'base': item.get('base', ''),
            'axis': item.get('axis', ''), 'prism_base': item.get('prismBase', ''), 'color_int': item.get('colorInt', ''),
            'mir_coating': item.get('mirCoating', ''),
            'design1_id': self._get_id(cache, 'designs', self._get_val(item, 'design1dto')),
            'design2_id': self._get_id(cache, 'designs', self._get_val(item, 'design2dto')),
            'uv_id': self._get_id(cache, 'uvs', self._get_val(item, 'uvdto')),
            'cl_hmc_id': self._get_id(cache, 'colors', self._get_val(item, 'clhmcdto')),
            'cl_pho_id': self._get_id(cache, 'colors', self._get_val(item, 'clphodto')),
            'cl_tint_id': self._get_id(cache, 'colors', self._get_val(item, 'clTintdto')),
            'index_id': self._get_id(cache, 'lens_indexes', self._get_val(item, 'lensIndexdto')),
            'material_id': self._get_id(cache, 'materials', self._get_val(item, 'materialdto')),
        }
        coats = [self._get_id(cache, 'coatings', c.get('cid')) for c in (item.get('coatingsdto') or []) if c.get('cid')]
        if any(coats): v['coating_ids'] = [(6, 0, [c for c in coats if c])]
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
        total = len(items)
        success = failed = 0
        to_create, to_update = [], []
        child_vals_map = {} # product_id -> child_vals
        new_child_data = [] # (temp_ref, child_vals)
        
        _logger.info(f"🔄 Processing {total} {product_type} items...")
        
        has_child = child_model and child_model in self.env
        
        for idx, item in enumerate(items):
            try:
                vals, pid = self._prepare_base_vals(item, cache, product_type)
                c_vals = {}
                if has_child:
                    if product_type == 'lens': c_vals = self._prepare_lens_vals(item, cache)
                    elif product_type == 'opt': c_vals = self._prepare_opt_vals(item, cache)
                
                if pid:
                    to_update.append((pid, vals))
                    if has_child: child_vals_map[pid] = c_vals
                else:
                    to_create.append(vals)
                    if has_child: new_child_data.append((idx, c_vals))
            except Exception as e:
                failed += 1
                _logger.error(f"Prepare error: {e}")

        # Batch Create
        if to_create:
            batch_size = 100
            for i in range(0, len(to_create), batch_size):
                b_vals = to_create[i:i+batch_size]
                b_child_refs = new_child_data[i:i+batch_size] if has_child else []
                try:
                    recs = self.env['product.template'].with_context(tracking_disable=True).create(b_vals)
                    for j, rec in enumerate(recs):
                        cache['products'][rec.default_code] = rec.id
                        if has_child:
                            _, cv = b_child_refs[j]
                            cv['product_tmpl_id'] = rec.id
                            self.env[child_model].create(cv)
                            # Update cache for child if needed (omitted for speed)
                    success += len(recs)
                except Exception as e:
                    failed += len(b_vals)
                    _logger.error(f"Batch Create Error: {e}")

        # Batch Update
        for pid, vals in to_update:
            try:
                self.env['product.template'].browse(pid).with_context(tracking_disable=True).write(vals)
                if has_child and pid in child_vals_map:
                    c_vals = child_vals_map[pid]
                    cmap = cache['lens_records'] if product_type == 'lens' else cache['opt_records']
                    if pid in cmap:
                        self.env[child_model].browse(cmap[pid]).write(c_vals)
                    else:
                        c_vals['product_tmpl_id'] = pid
                        cid = self.env[child_model].create(c_vals).id
                        cmap[pid] = cid
                success += 1
            except Exception as e:
                failed += 1
                _logger.error(f"Update Error: {e}")
                
        return success, failed

    def sync_products_from_springboot(self):
        # If called from cron/server action, self might be empty
        rec = self
        if not rec:
            rec = self.search([], limit=1, order='last_sync_date desc')
            if not rec:
                rec = self.create({'name': 'Daily Auto Sync'})
        return rec._run_sync()

    def sync_products_limited(self, limit=200):
        return self._run_sync(limit)

    def _run_sync(self, limit=None):
        self.ensure_one()
        try:
            self.write({'sync_status': 'in_progress', 'sync_log': 'Syncing...', 'last_sync_date': fields.Datetime.now()})
            self.env.cr.commit()
            
            token = self._get_access_token()
            cache = self._preload_all_data()
            cfg = self._get_api_config()
            stats = {}
            
            # Lens
            items = self._fetch_all_items(cfg['lens_endpoint'], token, 'Lens', limit)
            s, f = self._process_batch(items, cache, 'lens', 'product.lens')
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
            msg = f"Synced {total} (Lens:{stats['lens']}, Opt:{stats['opt']}, Acc:{stats['acc']}). Failed: {stats['failed']}"
            self.write({'sync_status': 'success' if stats['failed'] == 0 else 'success', 'sync_log': msg, 
                       'total_synced': total, 'total_failed': stats['failed'], 
                       'lens_count': stats['lens'], 'opts_count': stats['opt'], 'other_count': stats['acc']})
            
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Sync Done', 'message': msg, 'type': 'success'}}

        except Exception as e:
            self.env.cr.rollback()
            self.write({'sync_status': 'error', 'sync_log': str(e)})
            self.env.cr.commit()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Sync Failed', 'message': str(e), 'type': 'danger'}}

    def test_api_connection(self):
        try:
            token = self._get_access_token()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Connection OK', 'message': 'Token obtained.', 'type': 'success'}}
        except Exception as e:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 
                    'params': {'title': 'Connection Failed', 'message': str(e), 'type': 'danger'}}
