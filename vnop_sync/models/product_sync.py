# -*- coding: utf-8 -*-
import base64
import json
import logging
import os
from io import BytesIO
from collections import defaultdict

import requests
import urllib3
from PIL import Image

from odoo import models, fields, api, _
from odoo.exceptions import UserError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_logger = logging.getLogger(__name__)


class ProductSync(models.Model):
    _name = 'product.sync'
    _description = 'Product Synchronization'
    _order = 'last_sync_date desc'

    name = fields.Char('Sync Name', required=True, default='Product Sync')

    # Status tracking
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
            if total > 0:
                record.progress = (record.total_synced / total) * 100
            else:
                record.progress = 0

    @api.model
    def _get_api_config(self):
        return {
            'base_url': os.getenv('SPRING_BOOT_BASE_URL', 'https://localhost:8443'),
            'login_endpoint': os.getenv('API_LOGIN_ENDPOINT', '/api/auth/service-token'),
            # Product endpoints
            'lens_endpoint': os.getenv('API_LENS_ENDPOINT', '/api/product/lens'),
            'opts_endpoint': os.getenv('API_OPTS_ENDPOINT', '/api/product/opts'),
            'types_endpoint': os.getenv('API_TYPES_ENDPOINT', '/api/product/types'),
            # Credentials
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
                json={
                    'username': config['service_username'],
                    'password': config['service_password']
                },
                verify=config['ssl_verify'],
                timeout=config['login_timeout']
            )

            response.raise_for_status()
            data = response.json()
            token = data.get('token')

            if not token:
                raise UserError(_('Login failed: No token received'))

            _logger.info("✅ Token obtained successfully")
            return token

        except requests.exceptions.RequestException as e:
            error_msg = f"Authentication failed: {str(e)}"
            _logger.error(f"❌ {error_msg}")
            raise UserError(_(error_msg))

    def _fetch_paged_api(self, endpoint, token, page=0, size=100):
        """Fetch paginated API data"""
        config = self._get_api_config()
        url = f"{config['base_url']}{endpoint}?page={page}&size={size}"
        
        try:
            _logger.info(f"📡 Fetching: {url}")
            
            response = requests.get(
                url,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                },
                verify=config['ssl_verify'],
                timeout=config['api_timeout']
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"
            _logger.error(f"❌ {error_msg}")
            raise UserError(_(error_msg))

    def _fetch_all_pages(self, endpoint, token, product_type_name):
        """Fetch all pages from a paginated API endpoint"""
        all_items = []
        page = 0
        size = 100
        
        while True:
            result = self._fetch_paged_api(endpoint, token, page, size)
            
            content = result.get('content', [])
            if not content:
                break
                
            all_items.extend(content)
            
            total_pages = result.get('totalPages', 1)
            total_elements = result.get('totalElements', 0)
            
            _logger.info(f"📦 {product_type_name}: Page {page + 1}/{total_pages}, Got {len(content)} items (Total: {len(all_items)}/{total_elements})")
            
            page += 1
            if page >= total_pages:
                break
        
        return all_items

    def _fetch_limited_pages(self, endpoint, token, product_type_name, limit=200):
        """Fetch limited items from a paginated API endpoint"""
        all_items = []
        page = 0
        size = 100
        
        while len(all_items) < limit:
            result = self._fetch_paged_api(endpoint, token, page, size)
            
            content = result.get('content', [])
            if not content:
                break
                
            all_items.extend(content)
            
            total_elements = result.get('totalElements', 0)
            _logger.info(f"📦 {product_type_name}: Page {page + 1}, Got {len(content)} items (Total: {len(all_items)}/{min(limit, total_elements)})")
            
            page += 1
            
            # Stop if we have enough items
            if len(all_items) >= limit:
                all_items = all_items[:limit]
                break
        
        return all_items

    def _fetch_lens_products(self, token, limit=None):
        """Fetch lens products from /api/xnk/lens"""
        config = self._get_api_config()
        if limit:
            return self._fetch_limited_pages(config['lens_endpoint'], token, 'Lens', limit)
        return self._fetch_all_pages(config['lens_endpoint'], token, 'Lens')

    def _fetch_opts_products(self, token, limit=None):
        """Fetch optical products from /api/xnk/opts"""
        config = self._get_api_config()
        if limit:
            return self._fetch_limited_pages(config['opts_endpoint'], token, 'Optical', limit)
        return self._fetch_all_pages(config['opts_endpoint'], token, 'Optical')

    def _fetch_types_products(self, token, limit=None):
        """Fetch other products from /api/xnk/types"""
        config = self._get_api_config()
        if limit:
            return self._fetch_limited_pages(config['types_endpoint'], token, 'Types', limit)
        return self._fetch_all_pages(config['types_endpoint'], token, 'Types')

    def _preload_all_data(self):
        """Pre-load existing data for optimized lookup"""
        _logger.info("📦 Pre-loading existing data...")

        cache = {
            'products': {},
            'categories': {},
            'brands': {},
            'countries': {},
            'warranties': {},
            'taxes': {},
            'suppliers': {},
            'supplier_info': defaultdict(dict),
            # Lens-specific
            'designs': {},
            'materials': {},
            'uvs': {},
            'coatings': {},
            'colors': {},
            'lens_indexes': {},
            # OPT-specific
            'frames': {},
            'frame_types': {},
            'shapes': {},
            'ves': {},
            'temples': {},
            # Product type records
            'lens_records': {},
            'opt_records': {},
        }

        # Existing products by default_code
        products = self.env['product.template'].search_read(
            [('default_code', '!=', False)],
            ['id', 'default_code']
        )
        cache['products'] = {p['default_code']: p['id'] for p in products}
        _logger.info(f"  ✅ Loaded {len(cache['products'])} existing products")

        # Categories
        categories = self.env['product.category'].search_read(
            [],
            ['id', 'name', 'parent_id']
        )
        for cat in categories:
            parent_id = cat['parent_id'][0] if cat['parent_id'] else False
            cache['categories'][(cat['name'], parent_id)] = cat['id']
        _logger.info(f"  ✅ Loaded {len(cache['categories'])} categories")

        # Brands
        if 'xnk.brand' in self.env:
            brands = self.env['xnk.brand'].search_read([], ['id', 'code', 'name'])
            for b in brands:
                if b.get('code'):
                    cache['brands'][b['code'].upper()] = b['id']
                if b.get('name'):
                    cache['brands'][b['name'].upper()] = b['id']
            _logger.info(f"  ✅ Loaded {len(cache['brands'])} brands")

        # Countries
        if 'xnk.country' in self.env:
            countries = self.env['xnk.country'].search_read([], ['id', 'code'])
            cache['countries'] = {c['code'].upper(): c['id'] for c in countries if c.get('code')}
            _logger.info(f"  ✅ Loaded {len(cache['countries'])} countries")

        # Warranties
        if 'xnk.warranty' in self.env:
            warranties = self.env['xnk.warranty'].search_read([], ['id', 'code', 'name'])
            for w in warranties:
                if w.get('code'):
                    cache['warranties'][w['code'].upper()] = w['id']
                if w.get('name'):
                    cache['warranties'][w['name'].upper()] = w['id']
            _logger.info(f"  ✅ Loaded {len(cache['warranties'])} warranties")

        # Taxes
        taxes = self.env['account.tax'].search_read(
            [('type_tax_use', '=', 'sale')],
            ['id', 'name']
        )
        cache['taxes'] = {t['name']: t['id'] for t in taxes}
        _logger.info(f"  ✅ Loaded {len(cache['taxes'])} taxes")

        # Suppliers
        suppliers = self.env['res.partner'].search_read(
            [('ref', '!=', False), ('supplier_rank', '>', 0)],
            ['id', 'ref']
        )
        cache['suppliers'] = {s['ref'].upper() if s.get('ref') else '': s['id'] for s in suppliers}
        _logger.info(f"  ✅ Loaded {len(cache['suppliers'])} suppliers")

        # Lens-specific master data
        if 'product.design' in self.env:
            designs = self.env['product.design'].search_read([], ['id', 'cid'])
            cache['designs'] = {d['cid'].upper(): d['id'] for d in designs if d.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['designs'])} designs")

        if 'product.material' in self.env:
            materials = self.env['product.material'].search_read([], ['id', 'cid'])
            cache['materials'] = {m['cid'].upper(): m['id'] for m in materials if m.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['materials'])} materials")

        if 'product.uv' in self.env:
            uvs = self.env['product.uv'].search_read([], ['id', 'cid'])
            cache['uvs'] = {u['cid'].upper(): u['id'] for u in uvs if u.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['uvs'])} uvs")

        if 'product.coating' in self.env:
            coatings = self.env['product.coating'].search_read([], ['id', 'cid'])
            cache['coatings'] = {c['cid'].upper(): c['id'] for c in coatings if c.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['coatings'])} coatings")

        if 'product.cl' in self.env:
            colors = self.env['product.cl'].search_read([], ['id', 'cid'])
            cache['colors'] = {c['cid'].upper(): c['id'] for c in colors if c.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['colors'])} colors")

        if 'product.lens.index' in self.env:
            lens_indexes = self.env['product.lens.index'].search_read([], ['id', 'cid'])
            cache['lens_indexes'] = {li['cid'].upper(): li['id'] for li in lens_indexes if li.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['lens_indexes'])} lens indexes")

        # OPT-specific master data
        if 'product.frame' in self.env:
            frames = self.env['product.frame'].search_read([], ['id', 'cid'])
            cache['frames'] = {f['cid'].upper(): f['id'] for f in frames if f.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['frames'])} frames")

        if 'product.frame.type' in self.env:
            frame_types = self.env['product.frame.type'].search_read([], ['id', 'cid'])
            cache['frame_types'] = {ft['cid'].upper(): ft['id'] for ft in frame_types if ft.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['frame_types'])} frame types")

        if 'product.shape' in self.env:
            shapes = self.env['product.shape'].search_read([], ['id', 'cid'])
            cache['shapes'] = {s['cid'].upper(): s['id'] for s in shapes if s.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['shapes'])} shapes")

        if 'product.ve' in self.env:
            ves = self.env['product.ve'].search_read([], ['id', 'cid'])
            cache['ves'] = {v['cid'].upper(): v['id'] for v in ves if v.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['ves'])} ves")

        if 'product.temple' in self.env:
            temples = self.env['product.temple'].search_read([], ['id', 'cid'])
            cache['temples'] = {t['cid'].upper(): t['id'] for t in temples if t.get('cid')}
            _logger.info(f"  ✅ Loaded {len(cache['temples'])} temples")

        # Existing lens records
        if 'product.lens' in self.env:
            lens_recs = self.env['product.lens'].search_read([], ['id', 'product_tmpl_id'])
            for lr in lens_recs:
                if lr.get('product_tmpl_id'):
                    cache['lens_records'][lr['product_tmpl_id'][0]] = lr['id']
            _logger.info(f"  ✅ Loaded {len(cache['lens_records'])} lens records")

        # Existing opt records
        if 'product.opt' in self.env:
            opt_recs = self.env['product.opt'].search_read([], ['id', 'product_tmpl_id'])
            for opr in opt_recs:
                if opr.get('product_tmpl_id'):
                    cache['opt_records'][opr['product_tmpl_id'][0]] = opr['id']
            _logger.info(f"  ✅ Loaded {len(cache['opt_records'])} opt records")

        return cache

    def _get_or_create_from_cache(self, model_name, cache_key, code, name, cache, extra_vals=None):
        """Get existing record from cache or create new one"""
        if not code:
            return False
            
        code_upper = code.upper()
        if code_upper in cache[cache_key]:
            return cache[cache_key][code_upper]

        vals = {'name': name, 'code': code}
        if extra_vals:
            vals.update(extra_vals)

        new_record = self.env[model_name].create(vals)
        cache[cache_key][code_upper] = new_record.id

        return new_record.id

    def _get_category_from_cache(self, category_name, cache, parent_name=None):
        """Get or create category with caching"""
        if not category_name:
            return self.env.ref('product.product_category_all').id

        parent_id = False
        if parent_name:
            cache_key = (parent_name, False)
            if cache_key in cache['categories']:
                parent_id = cache['categories'][cache_key]
            else:
                parent = self.env['product.category'].create({'name': parent_name})
                parent_id = parent.id
                cache['categories'][cache_key] = parent_id

        cache_key = (category_name, parent_id)
        if cache_key in cache['categories']:
            return cache['categories'][cache_key]

        vals = {'name': category_name}
        if parent_id:
            vals['parent_id'] = parent_id

        category = self.env['product.category'].create(vals)
        cache['categories'][cache_key] = category.id

        return category.id

    def _prepare_base_product_vals(self, productdto, cache):
        """Prepare base product.template values from productdto"""
        if not isinstance(productdto, dict):
            raise ValueError("Invalid productdto")

        cid = productdto.get('cid', '').strip()
        if not cid:
            raise ValueError("Missing product CID")

        name = productdto.get('fullname') or 'Unknown Product'
        existing_product_id = cache['products'].get(cid)

        # Category from groupdto
        groupdto = productdto.get('groupdto') or {}
        group_type_dto = groupdto.get('groupTypedto') or {}
        group_type_name = group_type_dto.get('name', 'Khác')

        category_map = {
            'Mắt': ('Lens Products', 'lens'),
            'Gọng': ('Optical OPT', 'opt'),
            'Khác': ('Accessories', 'accessory')
        }

        main_category, product_type = category_map.get(
            group_type_name,
            ('Accessories', 'accessory')
        )

        categ_id = self._get_category_from_cache(
            groupdto.get('name', 'All Products'),
            cache,
            parent_name=main_category
        )

        # Brand
        brand_cid = (productdto.get('tmdto') or {}).get('cid')
        brand_name = (productdto.get('tmdto') or {}).get('name')
        brand_id = False
        if brand_cid and brand_name and 'xnk.brand' in self.env:
            brand_id = self._get_or_create_from_cache(
                'xnk.brand', 'brands', brand_cid, brand_name, cache
            )

        # Supplier
        supplierdto = productdto.get('supplierdto') or {}
        supplier_id = False
        supplier_details = supplierdto.get('supplierDetailDTOS', [])

        if supplier_details and len(supplier_details) > 0:
            detail = supplier_details[0]
            supplier_cid = detail.get('cid')
            supplier_name = detail.get('name')

            if supplier_cid and supplier_name:
                supplier_cid_upper = supplier_cid.upper()
                if supplier_cid_upper in cache['suppliers']:
                    supplier_id = cache['suppliers'][supplier_cid_upper]
                else:
                    supplier = self.env['res.partner'].create({
                        'name': supplier_name,
                        'ref': supplier_cid,
                        'supplier_rank': 1,
                        'is_company': True,
                        'phone': detail.get('phone', ''),
                        'email': detail.get('mail', ''),
                        'street': detail.get('address', ''),
                    })
                    supplier_id = supplier.id
                    cache['suppliers'][supplier_cid_upper] = supplier_id

        # Country
        country_cid = (productdto.get('codto') or {}).get('cid')
        country_name = (productdto.get('codto') or {}).get('name')
        country_id = False
        if country_cid and country_name and 'xnk.country' in self.env:
            country_id = self._get_or_create_from_cache(
                'xnk.country', 'countries', country_cid, country_name, cache
            )

        # Warranty
        warranty_dto = productdto.get('warrantydto')
        warranty_id = False
        if warranty_dto and isinstance(warranty_dto, dict):
            warranty_cid = warranty_dto.get('cid')
            warranty_name = warranty_dto.get('name')
            if warranty_cid and warranty_name and 'xnk.warranty' in self.env:
                warranty_id = self._get_or_create_from_cache(
                    'xnk.warranty', 'warranties', warranty_cid, warranty_name, cache,
                    extra_vals={
                        'description': warranty_dto.get('description', ''),
                        'value': int(warranty_dto.get('value', 0))
                    }
                )

        # Tax
        tax_percent = float(productdto.get('tax') or 0)
        tax_id = False
        if tax_percent and tax_percent > 0:
            tax_name = f"Tax {tax_percent}%"
            if tax_name in cache['taxes']:
                tax_id = cache['taxes'][tax_name]
            else:
                tax = self.env['account.tax'].create({
                    'name': tax_name,
                    'amount': tax_percent,
                    'amount_type': 'percent',
                    'type_tax_use': 'sale'
                })
                cache['taxes'][tax_name] = tax.id
                tax_id = tax.id

        taxes_ids = [(6, 0, [tax_id])] if tax_id else False

        # Prices
        rt_price = float(productdto.get('rtPrice') or 0)
        ws_price = float(productdto.get('wsPrice') or 0)
        ct_price = float(productdto.get('ctPrice') or 0)
        or_price = float(productdto.get('orPrice') or 0)

        uom_id = self.env.ref('uom.product_uom_unit').id

        vals = {
            'name': name,
            'default_code': cid,
            'type': 'consu',
            'categ_id': categ_id,
            'uom_id': uom_id,
            'uom_po_id': uom_id,
            'list_price': rt_price,
            'standard_price': or_price,
            'taxes_id': taxes_ids,
            'product_type': product_type,
        }

        # Add Many2one fields
        vals.update({
            'brand_id': brand_id,
            'supplier_id': supplier_id,
            'country_id': country_id,
            'warranty_id': warranty_id,
        })

        # Custom fields
        custom_fields = {
            'x_eng_name': productdto.get('engName', ''),
            'x_trade_name': productdto.get('tradeName', ''),
            'x_note_long': productdto.get('note', ''),
            'x_uses': productdto.get('uses', ''),
            'x_guide': productdto.get('guide', ''),
            'x_warning': productdto.get('warning', ''),
            'x_preserve': productdto.get('preserve', ''),
            'x_cid_ncc': productdto.get('cidNcc', ''),
            'x_accessory_total': int(productdto.get('accessoryTotal') or 0),
            'x_status_name': (productdto.get('statusProductdto') or {}).get('name', ''),
            'x_tax_percent': tax_percent,
            'x_currency_zone_code': (productdto.get('currencyZoneDTO') or {}).get('cid', ''),
            'x_currency_zone_value': float((productdto.get('currencyZoneDTO') or {}).get('value') or 0),
            'x_ws_price': ws_price,
            'x_ct_price': ct_price,
            'x_or_price': or_price,
            'x_group_type_name': group_type_name,
        }

        ProductTemplate = self.env['product.template']
        for field_name, field_value in custom_fields.items():
            if field_name in ProductTemplate._fields:
                vals[field_name] = field_value

        return vals, product_type, existing_product_id

    def _prepare_lens_vals(self, item, cache):
        """Prepare product.lens values from lens API item"""
        vals = {}
        
        # Direct fields
        vals['sph'] = item.get('sph', '')
        vals['cyl'] = item.get('cyl', '')
        vals['len_add'] = item.get('lensAdd', '')
        vals['diameter'] = item.get('diameter', '')
        vals['corridor'] = item.get('corridor', '')
        vals['abbe'] = item.get('abbe', '')
        vals['polarized'] = item.get('polarized', '')
        vals['prism'] = item.get('prism', '')
        vals['base'] = item.get('base', '')
        vals['axis'] = item.get('axis', '')
        vals['prism_base'] = item.get('prismBase', '')
        vals['color_int'] = item.get('colorInt', '')
        vals['mir_coating'] = item.get('mirCoating', '')
        
        # Many2one lookups
        design1dto = item.get('design1dto') or {}
        if design1dto.get('cid'):
            design1_cid = design1dto['cid'].upper()
            vals['design1_id'] = cache['designs'].get(design1_cid, False)
        
        design2dto = item.get('design2dto') or {}
        if design2dto.get('cid'):
            design2_cid = design2dto['cid'].upper()
            vals['design2_id'] = cache['designs'].get(design2_cid, False)
        
        uvdto = item.get('uvdto') or {}
        if uvdto.get('cid'):
            uv_cid = uvdto['cid'].upper()
            vals['uv_id'] = cache['uvs'].get(uv_cid, False)
        
        clhmcdto = item.get('clhmcdto') or {}
        if clhmcdto.get('cid'):
            clhmc_cid = clhmcdto['cid'].upper()
            vals['cl_hmc_id'] = cache['colors'].get(clhmc_cid, False)
        
        clphodto = item.get('clphodto') or {}
        if clphodto.get('cid'):
            clpho_cid = clphodto['cid'].upper()
            vals['cl_pho_id'] = cache['colors'].get(clpho_cid, False)
        
        cltintdto = item.get('clTintdto') or {}
        if cltintdto.get('cid'):
            cltint_cid = cltintdto['cid'].upper()
            vals['cl_tint_id'] = cache['colors'].get(cltint_cid, False)
        
        lensindexdto = item.get('lensIndexdto') or {}
        if lensindexdto.get('cid'):
            lensindex_cid = lensindexdto['cid'].upper()
            vals['index_id'] = cache['lens_indexes'].get(lensindex_cid, False)
        
        materialdto = item.get('materialdto') or {}
        if materialdto.get('cid'):
            material_cid = materialdto['cid'].upper()
            vals['material_id'] = cache['materials'].get(material_cid, False)
        
        # Many2many coatings
        coatingsdto = item.get('coatingsdto') or []
        coating_ids = []
        for coat in coatingsdto:
            if coat.get('cid'):
                coat_cid = coat['cid'].upper()
                coat_id = cache['coatings'].get(coat_cid)
                if coat_id:
                    coating_ids.append(coat_id)
        if coating_ids:
            vals['coating_ids'] = [(6, 0, coating_ids)]
        
        return vals

    def _prepare_opt_vals(self, item, cache):
        """Prepare product.opt values from opts API item"""
        vals = {}
        
        # Direct fields
        vals['season'] = item.get('season', '')
        vals['model'] = item.get('model', '')
        vals['serial'] = item.get('serial', '')
        vals['oem_ncc'] = item.get('oemNcc', '')
        vals['sku'] = item.get('sku', '')
        vals['color'] = item.get('color', '')
        
        # Gender (1=Male, 2=Female, 3=Unisex)
        gender = item.get('gender')
        if gender:
            vals['gender'] = str(gender)
        
        # Integer dimensions
        vals['temple_width'] = int(item.get('templeWidth') or 0)
        vals['lens_width'] = int(item.get('lensWidth') or 0)
        vals['lens_span'] = int(item.get('lensSpan') or 0)
        vals['lens_height'] = int(item.get('lensHeight') or 0)
        vals['bridge_width'] = int(item.get('bridgeWidth') or 0)
        
        # Many2one lookups
        colorlensdto = item.get('colorLensdto') or {}
        if colorlensdto.get('cid'):
            colorlens_cid = colorlensdto['cid'].upper()
            vals['color_lens_id'] = cache['colors'].get(colorlens_cid, False)
        
        framedto = item.get('framedto') or {}
        if framedto.get('cid'):
            frame_cid = framedto['cid'].upper()
            vals['frame_id'] = cache['frames'].get(frame_cid, False)
        
        frametypedto = item.get('frameTypedto') or {}
        if frametypedto.get('cid'):
            frametype_cid = frametypedto['cid'].upper()
            vals['frame_type_id'] = cache['frame_types'].get(frametype_cid, False)
        
        shapedto = item.get('shapedto') or {}
        if shapedto.get('cid'):
            shape_cid = shapedto['cid'].upper()
            vals['shape_id'] = cache['shapes'].get(shape_cid, False)
        
        vedto = item.get('vedto') or {}
        if vedto.get('cid'):
            ve_cid = vedto['cid'].upper()
            vals['ve_id'] = cache['ves'].get(ve_cid, False)
        
        templedto = item.get('templedto') or {}
        if templedto.get('cid'):
            temple_cid = templedto['cid'].upper()
            vals['temple_id'] = cache['temples'].get(temple_cid, False)
        
        # Materials
        materialvedto = item.get('materialVedto') or {}
        if materialvedto.get('cid'):
            materialve_cid = materialvedto['cid'].upper()
            vals['material_ve_id'] = cache['materials'].get(materialve_cid, False)
        
        materialtempletipdto = item.get('materialTempleTipdto') or {}
        if materialtempletipdto.get('cid'):
            materialtempletip_cid = materialtempletipdto['cid'].upper()
            vals['material_temple_tip_id'] = cache['materials'].get(materialtempletip_cid, False)
        
        materiallensdto = item.get('materialLensdto') or {}
        if materiallensdto.get('cid'):
            materiallens_cid = materiallensdto['cid'].upper()
            vals['material_lens_id'] = cache['materials'].get(materiallens_cid, False)
        
        # Many2many coatings
        coatingsdto = item.get('coatingsdto') or []
        coating_ids = []
        for coat in coatingsdto:
            if coat.get('cid'):
                coat_cid = coat['cid'].upper()
                coat_id = cache['coatings'].get(coat_cid)
                if coat_id:
                    coating_ids.append(coat_id)
        if coating_ids:
            vals['coating_ids'] = [(6, 0, coating_ids)]
        
        return vals

    def _process_lens_products(self, items, cache):
        """Process lens products from API - OPTIMIZED with batch operations"""
        success = 0
        failed = 0
        total = len(items)
        
        # Check if product.lens model exists (vnoptic_product installed)
        has_lens_model = 'product.lens' in self.env
        
        # Prepare all data first
        to_create = []
        to_update = []
        lens_to_create = []
        lens_to_update = []
        
        _logger.info(f"🔄 Preparing {total} lens products...")
        
        for idx, item in enumerate(items):
            try:
                productdto = item.get('productdto') or {}
                if not productdto:
                    failed += 1
                    continue
                
                base_vals, product_type, existing_id = self._prepare_base_product_vals(productdto, cache)
                base_vals['product_type'] = 'lens'
                
                if existing_id:
                    to_update.append((existing_id, base_vals, item))
                else:
                    to_create.append((base_vals, item))
                    
            except Exception as e:
                failed += 1
                cid = (item.get('productdto') or {}).get('cid', 'Unknown')
                _logger.error(f"❌ Error preparing lens {cid}: {e}")
        
        _logger.info(f"📦 Lens: {len(to_create)} to create, {len(to_update)} to update")
        
        # Batch CREATE new products
        if to_create:
            _logger.info(f"⚡ Batch creating {len(to_create)} new products...")
            batch_size = 100
            for i in range(0, len(to_create), batch_size):
                batch = to_create[i:i+batch_size]
                vals_list = [v[0] for v in batch]
                try:
                    new_products = self.env['product.template'].with_context(tracking_disable=True).create(vals_list)
                    for j, product in enumerate(new_products):
                        cache['products'][vals_list[j]['default_code']] = product.id
                        if has_lens_model:
                            lens_to_create.append((product.id, batch[j][1]))
                    success += len(new_products)
                except Exception as e:
                    _logger.error(f"❌ Batch create error: {e}")
                    failed += len(batch)
                
                if (i + batch_size) % 500 == 0 or i + batch_size >= len(to_create):
                    _logger.info(f"  ✅ Created {min(i+batch_size, len(to_create))}/{len(to_create)} products")
        
        # Batch UPDATE existing products
        if to_update:
            _logger.info(f"⚡ Updating {len(to_update)} existing products...")
            for idx, (existing_id, vals, item) in enumerate(to_update):
                try:
                    product = self.env['product.template'].browse(existing_id)
                    product.with_context(tracking_disable=True).write(vals)
                    if has_lens_model:
                        if existing_id in cache.get('lens_records', {}):
                            lens_to_update.append((cache['lens_records'][existing_id], item))
                        else:
                            lens_to_create.append((existing_id, item))
                    success += 1
                except Exception as e:
                    failed += 1
                    _logger.error(f"❌ Update error: {e}")
                
                if (idx + 1) % 500 == 0:
                    _logger.info(f"  ✅ Updated {idx+1}/{len(to_update)} products")
        
        # Batch CREATE lens records
        if has_lens_model and lens_to_create:
            _logger.info(f"⚡ Creating {len(lens_to_create)} lens records...")
            batch_size = 100
            for i in range(0, len(lens_to_create), batch_size):
                batch = lens_to_create[i:i+batch_size]
                vals_list = []
                for product_id, item in batch:
                    lens_vals = self._prepare_lens_vals(item, cache)
                    lens_vals['product_tmpl_id'] = product_id
                    vals_list.append(lens_vals)
                try:
                    new_lens = self.env['product.lens'].with_context(tracking_disable=True).create(vals_list)
                    for j, lens in enumerate(new_lens):
                        cache['lens_records'][batch[j][0]] = lens.id
                except Exception as e:
                    _logger.error(f"❌ Lens batch create error: {e}")
        
        _logger.info(f"✅ Lens processing complete: {success} success, {failed} failed")
        return success, failed

    def _process_opts_products(self, items, cache):
        """Process optical products from API - OPTIMIZED with batch operations"""
        success = 0
        failed = 0
        total = len(items)
        
        has_opt_model = 'product.opt' in self.env
        
        to_create = []
        to_update = []
        opt_to_create = []
        
        _logger.info(f"🔄 Preparing {total} optical products...")
        
        for idx, item in enumerate(items):
            try:
                productdto = item.get('productdto') or {}
                if not productdto:
                    failed += 1
                    continue
                
                base_vals, product_type, existing_id = self._prepare_base_product_vals(productdto, cache)
                base_vals['product_type'] = 'opt'
                
                if existing_id:
                    to_update.append((existing_id, base_vals, item))
                else:
                    to_create.append((base_vals, item))
                    
            except Exception as e:
                failed += 1
                cid = (item.get('productdto') or {}).get('cid', 'Unknown')
                _logger.error(f"❌ Error preparing opt {cid}: {e}")
        
        _logger.info(f"📦 Optical: {len(to_create)} to create, {len(to_update)} to update")
        
        # Batch CREATE new products
        if to_create:
            _logger.info(f"⚡ Batch creating {len(to_create)} new optical products...")
            batch_size = 100
            for i in range(0, len(to_create), batch_size):
                batch = to_create[i:i+batch_size]
                vals_list = [v[0] for v in batch]
                try:
                    new_products = self.env['product.template'].with_context(tracking_disable=True).create(vals_list)
                    for j, product in enumerate(new_products):
                        cache['products'][vals_list[j]['default_code']] = product.id
                        if has_opt_model:
                            opt_to_create.append((product.id, batch[j][1]))
                    success += len(new_products)
                except Exception as e:
                    _logger.error(f"❌ Batch create error: {e}")
                    failed += len(batch)
                
                if (i + batch_size) % 500 == 0 or i + batch_size >= len(to_create):
                    _logger.info(f"  ✅ Created {min(i+batch_size, len(to_create))}/{len(to_create)} products")
        
        # Batch UPDATE existing products
        if to_update:
            _logger.info(f"⚡ Updating {len(to_update)} existing optical products...")
            for idx, (existing_id, vals, item) in enumerate(to_update):
                try:
                    product = self.env['product.template'].browse(existing_id)
                    product.with_context(tracking_disable=True).write(vals)
                    if has_opt_model:
                        if existing_id not in cache.get('opt_records', {}):
                            opt_to_create.append((existing_id, item))
                    success += 1
                except Exception as e:
                    failed += 1
                    _logger.error(f"❌ Update error: {e}")
                
                if (idx + 1) % 500 == 0:
                    _logger.info(f"  ✅ Updated {idx+1}/{len(to_update)} products")
        
        # Batch CREATE opt records
        if has_opt_model and opt_to_create:
            _logger.info(f"⚡ Creating {len(opt_to_create)} opt records...")
            batch_size = 100
            for i in range(0, len(opt_to_create), batch_size):
                batch = opt_to_create[i:i+batch_size]
                vals_list = []
                for product_id, item in batch:
                    opt_vals = self._prepare_opt_vals(item, cache)
                    opt_vals['product_tmpl_id'] = product_id
                    vals_list.append(opt_vals)
                try:
                    new_opts = self.env['product.opt'].with_context(tracking_disable=True).create(vals_list)
                    for j, opt in enumerate(new_opts):
                        cache['opt_records'][batch[j][0]] = opt.id
                except Exception as e:
                    _logger.error(f"❌ Opt batch create error: {e}")
        
        _logger.info(f"✅ Optical processing complete: {success} success, {failed} failed")
        return success, failed

    def _process_types_products(self, items, cache):
        """Process other products (accessories) from API - OPTIMIZED"""
        success = 0
        failed = 0
        total = len(items)
        
        to_create = []
        to_update = []
        
        _logger.info(f"🔄 Preparing {total} accessory products...")
        
        for idx, item in enumerate(items):
            try:
                productdto = item.get('productdto') or {}
                if not productdto:
                    failed += 1
                    continue
                
                base_vals, product_type, existing_id = self._prepare_base_product_vals(productdto, cache)
                base_vals['product_type'] = 'accessory'
                
                if existing_id:
                    to_update.append((existing_id, base_vals))
                else:
                    to_create.append(base_vals)
                    
            except Exception as e:
                failed += 1
                cid = (item.get('productdto') or {}).get('cid', 'Unknown')
                _logger.error(f"❌ Error preparing type {cid}: {e}")
        
        _logger.info(f"📦 Accessories: {len(to_create)} to create, {len(to_update)} to update")
        
        # Batch CREATE new products
        if to_create:
            _logger.info(f"⚡ Batch creating {len(to_create)} new accessory products...")
            batch_size = 100
            for i in range(0, len(to_create), batch_size):
                batch = to_create[i:i+batch_size]
                try:
                    new_products = self.env['product.template'].with_context(tracking_disable=True).create(batch)
                    for product in new_products:
                        cache['products'][product.default_code] = product.id
                    success += len(new_products)
                except Exception as e:
                    _logger.error(f"❌ Batch create error: {e}")
                    failed += len(batch)
                
                if (i + batch_size) % 500 == 0 or i + batch_size >= len(to_create):
                    _logger.info(f"  ✅ Created {min(i+batch_size, len(to_create))}/{len(to_create)} products")
        
        # Batch UPDATE existing products
        if to_update:
            _logger.info(f"⚡ Updating {len(to_update)} existing accessory products...")
            for idx, (existing_id, vals) in enumerate(to_update):
                try:
                    product = self.env['product.template'].browse(existing_id)
                    product.with_context(tracking_disable=True).write(vals)
                    success += 1
                except Exception as e:
                    failed += 1
                    _logger.error(f"❌ Update error: {e}")
                
                if (idx + 1) % 500 == 0:
                    _logger.info(f"  ✅ Updated {idx+1}/{len(to_update)} products")
        
        _logger.info(f"✅ Accessory processing complete: {success} success, {failed} failed")
        return success, failed

    def sync_products_from_springboot(self):
        """Main sync method - syncs all products from 3 APIs simultaneously"""
        self.ensure_one()

        try:
            # Update status
            self.write({
                'sync_status': 'in_progress',
                'sync_log': 'Starting sync...'
            })
            self.env.cr.commit()

            _logger.info("=" * 80)
            _logger.info("🚀 Starting product sync (all 3 APIs)...")

            token = self._get_access_token()
            cache = self._preload_all_data()

            stats = {'lens': 0, 'opt': 0, 'accessory': 0}
            total_success = 0
            total_failed = 0

            # Sync all 3 APIs
            _logger.info("📦 Fetching Lens products...")
            lens_items = self._fetch_lens_products(token)
            _logger.info(f"  Found {len(lens_items)} lens items")
            success, failed = self._process_lens_products(lens_items, cache)
            stats['lens'] = success
            total_success += success
            total_failed += failed
            self.env.cr.commit()

            _logger.info("📦 Fetching Optical products...")
            opts_items = self._fetch_opts_products(token)
            _logger.info(f"  Found {len(opts_items)} optical items")
            success, failed = self._process_opts_products(opts_items, cache)
            stats['opt'] = success
            total_success += success
            total_failed += failed
            self.env.cr.commit()

            _logger.info("📦 Fetching Other products...")
            types_items = self._fetch_types_products(token)
            _logger.info(f"  Found {len(types_items)} other items")
            success, failed = self._process_types_products(types_items, cache)
            stats['accessory'] = success
            total_success += success
            total_failed += failed
            self.env.cr.commit()

            log_message = self._generate_sync_log(total_success, total_failed, stats)

            self.write({
                'last_sync_date': fields.Datetime.now(),
                'sync_status': 'success',
                'total_synced': total_success,
                'total_failed': total_failed,
                'lens_count': stats['lens'],
                'opts_count': stats['opt'],
                'other_count': stats['accessory'],
                'sync_log': log_message
            })

            self.env.cr.commit()

            _logger.info("=" * 80)
            _logger.info(f"✅ SYNC COMPLETED: {total_success} OK, {total_failed} failed")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('✅ Sync Successful'),
                    'message': f'Synced {total_success} products! ({stats["lens"]} Lens, {stats["opt"]} OPT, {stats["accessory"]} Accessories)',
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"❌ Sync failed: {error_msg}")
            _logger.exception("Full traceback:")

            self.write({
                'sync_status': 'error',
                'sync_log': f"❌ ERROR:\n\n{error_msg}"
            })
            self.env.cr.commit()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('❌ Sync Failed'),
                    'message': error_msg[:200],
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def sync_products_limited(self, limit=200):
        """Test sync method - syncs limited products (200 per type by default)"""
        self.ensure_one()

        try:
            self.write({
                'sync_status': 'in_progress',
                'sync_log': f'Starting LIMITED sync ({limit} per type)...'
            })
            self.env.cr.commit()

            _logger.info("=" * 80)
            _logger.info(f"🧪 Starting LIMITED product sync ({limit} per type)...")

            token = self._get_access_token()
            cache = self._preload_all_data()

            stats = {'lens': 0, 'opt': 0, 'accessory': 0}
            total_success = 0
            total_failed = 0

            # Sync Lens (limited)
            _logger.info(f"📦 Fetching Lens products (limit {limit})...")
            lens_items = self._fetch_lens_products(token, limit=limit)
            _logger.info(f"  Processing {len(lens_items)} lens items")
            success, failed = self._process_lens_products(lens_items, cache)
            stats['lens'] = success
            total_success += success
            total_failed += failed
            self.env.cr.commit()

            # Sync Optical (limited)
            _logger.info(f"📦 Fetching Optical products (limit {limit})...")
            opts_items = self._fetch_opts_products(token, limit=limit)
            _logger.info(f"  Processing {len(opts_items)} optical items")
            success, failed = self._process_opts_products(opts_items, cache)
            stats['opt'] = success
            total_success += success
            total_failed += failed
            self.env.cr.commit()

            # Sync Accessories (limited)
            _logger.info(f"📦 Fetching Accessory products (limit {limit})...")
            types_items = self._fetch_types_products(token, limit=limit)
            _logger.info(f"  Processing {len(types_items)} accessory items")
            success, failed = self._process_types_products(types_items, cache)
            stats['accessory'] = success
            total_success += success
            total_failed += failed
            self.env.cr.commit()

            log_message = f"""🧪 LIMITED SYNC COMPLETED!

Total: {total_success} synced, {total_failed} failed
Limit: {limit} per type

Categories:
  • Lens: {stats['lens']}
  • OPT: {stats['opt']}
  • Accessories: {stats['accessory']}

Date: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

            self.write({
                'last_sync_date': fields.Datetime.now(),
                'sync_status': 'success',
                'total_synced': total_success,
                'total_failed': total_failed,
                'lens_count': stats['lens'],
                'opts_count': stats['opt'],
                'other_count': stats['accessory'],
                'sync_log': log_message
            })

            self.env.cr.commit()
            _logger.info(f"✅ LIMITED SYNC COMPLETED: {total_success} OK, {total_failed} failed")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('✅ Limited Sync Successful'),
                    'message': f'Synced {total_success}/{limit*3} products! ({stats["lens"]} Lens, {stats["opt"]} OPT, {stats["accessory"]} Accessories)',
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"❌ Limited sync failed: {error_msg}")

            self.write({
                'sync_status': 'error',
                'sync_log': f"❌ ERROR:\n\n{error_msg}"
            })
            self.env.cr.commit()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('❌ Limited Sync Failed'),
                    'message': error_msg[:200],
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _generate_sync_log(self, success, failed, stats):
        """Generate sync log message"""
        total = success + failed
        success_rate = (success / total * 100) if total > 0 else 0

        return f"""✅ SYNC COMPLETED!

Total: {success} synced, {failed} failed ({success_rate:.1f}% success)

Categories:
  • Lens: {stats['lens']}
  • OPT: {stats['opt']}
  • Accessories: {stats['accessory']}

Date: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    def test_api_connection(self):
        """Test API connection"""
        self.ensure_one()

        try:
            token = self._get_access_token()
            
            # Test each endpoint
            config = self._get_api_config()
            results = []
            
            for endpoint_name, endpoint in [
                ('Lens', config['lens_endpoint']),
                ('Optical', config['opts_endpoint']),
                ('Types', config['types_endpoint'])
            ]:
                try:
                    result = self._fetch_paged_api(endpoint, token, 0, 1)
                    total = result.get('totalElements', 0)
                    results.append(f"{endpoint_name}: {total} items")
                except Exception as e:
                    results.append(f"{endpoint_name}: Error - {str(e)[:50]}")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('✅ Connection Successful'),
                    'message': '\n'.join(results),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('❌ Connection Failed'),
                    'message': str(e)[:200],
                    'type': 'danger',
                    'sticky': True,
                }
            }
