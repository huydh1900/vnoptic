# -*- coding: utf-8 -*-
"""
Master data cache for Excel import
Loads all master data into memory to avoid N+1 queries during import
"""
import re

from odoo import _


class MasterDataCache:
    """Cache for master data lookup during import"""
    
    def __init__(self, env):
        """
        Initialize cache and load all master data
        
        Args:
            env: Odoo environment
        """
        self.env = env
        self._load_all_caches()
    
    def _load_all_caches(self):
        """Load all master data tables into cache dictionaries"""
        # Dedicated resolver maps for fields that frequently use business shorthand
        self.countries_code = {}
        self.countries_name = {}
        self.countries_alias = {}

        self.suppliers_code = {}
        self.suppliers_ref = {}
        self.suppliers_name = {}
        self.suppliers_alias = {}

        self.designs_code = {}
        self.designs_name = {}
        self.designs_alias = {}

        self.materials_code = {}
        self.materials_name = {}
        self.materials_alias = {}

        self.accessory_colors_code = {}
        self.accessory_colors_name = {}
        self.accessory_colors_alias = {}

        self.lens_materials_name = {}
        self.lens_materials_code = {}
        self.lens_materials_alias = {}

        # Product groups (by CID)
        self.groups = {}
        for g in self.env['product.group'].search([]):
            if g.cid:
                self.groups[self._normalize_value(g.cid)] = g
        
        # Brands (by code and name as fallback)
        self.brands = {}
        for b in self.env['product.brand'].search([]):
            # Index by code if available
            if hasattr(b, 'code') and b.code:
                self.brands[self._normalize_value(b.code)] = b
            # Also index by name for fallback
            if b.name:
                self.brands[self._normalize_value(b.name)] = b
        
        # Countries (by code)
        self.countries = {}
        for c in self.env['product.country'].search([]):
            if c.code:
                code_key = self._normalize_value(c.code)
                self.countries[code_key] = c
                self.countries_code[code_key] = c
                self.countries_alias[self._normalize_alias(c.code)] = c
            if c.name:
                name_key = self._normalize_value(c.name)
                self.countries_name[name_key] = c
                self.countries_alias[self._normalize_alias(c.name)] = c
        
        # Currencies (by name/code)
        self.currencies = {}
        for curr in self.env['res.currency'].search([]):
            if curr.name:
                self.currencies[self._normalize_value(curr.name)] = curr
        
        # Warranties (by code)
        self.warranties = {}
        for w in self.env['product.warranty'].search([]):
            if hasattr(w, 'code') and w.code:
                self.warranties[self._normalize_value(w.code)] = w
            # Also index by name for fallback
            if w.name:
                self.warranties[self._normalize_value(w.name)] = w
        
        # Suppliers (by ref, which is the actual column in res.partner)
        self.suppliers = {}
        partners = self.env['res.partner'].search([])
        for p in partners:
            # Prioritize explicit business codes first
            if hasattr(p, 'code') and p.code:
                code_key = self._normalize_value(p.code)
                self.suppliers[code_key] = p
                self.suppliers_code[code_key] = p
                self.suppliers_alias[self._normalize_alias(p.code)] = p

            # Index by ref field (legacy/internal vendor reference)
            if hasattr(p, 'ref') and p.ref:
                ref_key = self._normalize_value(p.ref)
                self.suppliers[ref_key] = p
                self.suppliers_ref[ref_key] = p
                self.suppliers_alias[self._normalize_alias(p.ref)] = p

            # Also index by name for fallback
            if p.name:
                name_key = self._normalize_value(p.name)
                self.suppliers[name_key] = p
                self.suppliers_name[name_key] = p
                self.suppliers_alias[self._normalize_alias(p.name)] = p
        
        # Lens-specific master data
        self.designs = {}
        for d in self.env['product.design'].search([]):
            if d.cid:
                cid_key = self._normalize_value(d.cid)
                self.designs[cid_key] = d
                self.designs_code[cid_key] = d
                self.designs_alias[self._normalize_alias(d.cid)] = d
            if hasattr(d, 'code') and d.code:
                code_key = self._normalize_value(d.code)
                self.designs[code_key] = d
                self.designs_code[code_key] = d
                self.designs_alias[self._normalize_alias(d.code)] = d
            if d.name:
                name_key = self._normalize_value(d.name)
                self.designs_name[name_key] = d
                self.designs_alias[self._normalize_alias(d.name)] = d
        
        self.materials = {}
        for m in self.env['product.material'].search([]):
            if m.cid:
                cid_key = self._normalize_value(m.cid)
                self.materials[cid_key] = m
                self.materials_code[cid_key] = m
                self.materials_alias[self._normalize_alias(m.cid)] = m
            if hasattr(m, 'code') and m.code:
                code_key = self._normalize_value(m.code)
                self.materials[code_key] = m
                self.materials_code[code_key] = m
                self.materials_alias[self._normalize_alias(m.code)] = m
            if m.name:
                name_key = self._normalize_value(m.name)
                self.materials_name[name_key] = m
                self.materials_alias[self._normalize_alias(m.name)] = m

        # Lens material master (model is different from accessory material)
        for lm in self.env['product.lens.material'].search([]):
            if hasattr(lm, 'code') and lm.code:
                code_key = self._normalize_value(lm.code)
                self.lens_materials_code[code_key] = lm
                self.lens_materials_alias[self._normalize_alias(lm.code)] = lm
            if hasattr(lm, 'cid') and lm.cid:
                cid_key = self._normalize_value(lm.cid)
                self.lens_materials_code[cid_key] = lm
                self.lens_materials_alias[self._normalize_alias(lm.cid)] = lm
            if lm.name:
                name_key = self._normalize_value(lm.name)
                self.lens_materials_name[name_key] = lm
                self.lens_materials_alias[self._normalize_alias(lm.name)] = lm
        
        self.uvs = {}
        for u in self.env['product.uv'].search([]):
            if u.cid:
                self.uvs[self._normalize_value(u.cid)] = u
        
        self.coatings = {}
        for c in self.env['product.coating'].search([]):
            if c.cid:
                self.coatings[self._normalize_value(c.cid)] = c
        
        self.colors = {}  # product.cl  
        for cl in self.env['product.cl'].search([]):
            if cl.cid:
                self.colors[self._normalize_value(cl.cid)] = cl
        
        self.lens_indexes = {}
        for li in self.env['product.lens.index'].search([]):
            if li.cid:
                self.lens_indexes[self._normalize_value(li.cid)] = li
        
        # OPT-specific master data
        self.frames = {}
        for f in self.env['product.frame'].search([]):
            if f.cid:
                self.frames[self._normalize_value(f.cid)] = f
        
        self.frame_types = {}
        for ft in self.env['product.frame.type'].search([]):
            if ft.cid:
                self.frame_types[self._normalize_value(ft.cid)] = ft
        
        self.shapes = {}
        for s in self.env['product.shape'].search([]):
            if s.cid:
                self.shapes[self._normalize_value(s.cid)] = s
        
        self.ves = {}
        for v in self.env['product.ve'].search([]):
            if v.cid:
                self.ves[self._normalize_value(v.cid)] = v
        
        self.temples = {}
        for t in self.env['product.temple'].search([]):
            if t.cid:
                self.temples[self._normalize_value(t.cid)] = t

        # Accessory-specific master data
        for c in self.env['product.color'].search([]):
            if c.cid:
                cid_key = self._normalize_value(c.cid)
                self.accessory_colors_code[cid_key] = c
                self.accessory_colors_alias[self._normalize_alias(c.cid)] = c
            if hasattr(c, 'code') and c.code:
                code_key = self._normalize_value(c.code)
                self.accessory_colors_code[code_key] = c
                self.accessory_colors_alias[self._normalize_alias(c.code)] = c
            if c.name:
                name_key = self._normalize_value(c.name)
                self.accessory_colors_name[name_key] = c
                self.accessory_colors_alias[self._normalize_alias(c.name)] = c

    def _normalize_value(self, value):
        """Normalize lookup values so Excel/business shorthand can be resolved consistently."""
        if value in (None, False):
            return ''
        text = str(value).strip()
        if not text:
            return ''
        return ' '.join(text.split()).upper()

    def _normalize_alias(self, value):
        """Aggressive alias normalization: remove separators and keep alphanumerics only."""
        normalized = self._normalize_value(value)
        if not normalized:
            return ''
        return re.sub(r'[^0-9A-Z]+', '', normalized)

    def _resolve_with_priority(self, value, primary_map, secondary_map=None, tertiary_map=None, alias_map=None):
        key = self._normalize_value(value)
        if not key:
            return None

        if primary_map:
            record = primary_map.get(key)
            if record:
                return record

        if secondary_map:
            record = secondary_map.get(key)
            if record:
                return record

        if tertiary_map:
            record = tertiary_map.get(key)
            if record:
                return record

        if alias_map:
            return alias_map.get(self._normalize_alias(value))

        return None
    
    def get(self, cache_dict, cid, raise_on_error=False, error_msg=None):
        """
        Get record from cache
        
        Args:
            cache_dict: Cache dictionary to lookup in
            cid: CID/Code to lookup
            raise_on_error: If True, raise error when not found
            error_msg: Custom error message
        
        Returns:
            Record or None
        
        Raises:
            ValueError: If raise_on_error=True and record not found
        """
        if not cid:
            return None
        
        key = self._normalize_value(cid)
        record = cache_dict.get(key)
        
        if not record and raise_on_error:
            msg = error_msg or f"Record not found: {cid}"
            raise ValueError(msg)
        
        return record
    
    def get_group(self, cid):
        """Get product group by CID"""
        return self.get(self.groups, cid)
    
    def get_brand(self, cid):
        """Get brand by CID"""
        return self.get(self.brands, cid)
    
    def get_country(self, code):
        """Get country by code > name > alias"""
        return self._resolve_with_priority(
            code,
            primary_map=self.countries_code,
            secondary_map=self.countries_name,
            alias_map=self.countries_alias,
        )
    
    def get_currency(self, name):
        """Get currency by name"""
        return self.get(self.currencies, name)
    
    def get_warranty(self, cid):
        """Get warranty by CID"""
        return self.get(self.warranties, cid)
    
    def get_supplier(self, cid_or_name):
        """Get supplier by code > ref > name > alias"""
        return self._resolve_with_priority(
            cid_or_name,
            primary_map=self.suppliers_code,
            secondary_map=self.suppliers_ref,
            tertiary_map=self.suppliers_name,
            alias_map=self.suppliers_alias,
        )
    
    def get_design(self, cid):
        """Get design by code/cid > name > alias"""
        return self._resolve_with_priority(
            cid,
            primary_map=self.designs_code,
            secondary_map=self.designs_name,
            alias_map=self.designs_alias,
        )
    
    def get_material(self, cid):
        """Get material by code/cid > name > alias"""
        return self._resolve_with_priority(
            cid,
            primary_map=self.materials_code,
            secondary_map=self.materials_name,
            alias_map=self.materials_alias,
        )

    def get_lens_material(self, value):
        """Get lens material by code/cid > name > alias (product.lens.material)."""
        return self._resolve_with_priority(
            value,
            primary_map=self.lens_materials_code,
            secondary_map=self.lens_materials_name,
            alias_map=self.lens_materials_alias,
        )
    
    def get_uv(self, cid):
        """Get UV by CID"""
        return self.get(self.uvs, cid)
    
    def get_coating(self, cid):
        """Get coating by CID"""
        return self.get(self.coatings, cid)
    
    def get_color(self, cid):
        """Get color/CL by CID"""
        return self.get(self.colors, cid)
    
    def get_lens_index(self, cid):
        """Get lens index by CID"""
        return self.get(self.lens_indexes, cid)
    
    def get_frame(self, cid):
        """Get frame by CID"""
        return self.get(self.frames, cid)
    
    def get_frame_type(self, cid):
        """Get frame type by CID"""
        return self.get(self.frame_types, cid)
    
    def get_shape(self, cid):
        """Get shape by CID"""
        return self.get(self.shapes, cid)
    
    def get_ve(self, cid):
        """Get ve by CID"""
        return self.get(self.ves, cid)
    
    def get_temple(self, cid):
        """Get temple by CID"""
        return self.get(self.temples, cid)

    def get_accessory_color(self, value):
        """Get accessory color (product.color) by code/cid > name > alias."""
        return self._resolve_with_priority(
            value,
            primary_map=self.accessory_colors_code,
            secondary_map=self.accessory_colors_name,
            alias_map=self.accessory_colors_alias,
        )
