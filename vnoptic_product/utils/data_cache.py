# -*- coding: utf-8 -*-
"""
Master data cache for Excel import
Loads all master data into memory to avoid N+1 queries during import
"""
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
        # Product groups (by CID)
        self.groups = {}
        for g in self.env['product.group'].search([]):
            if g.cid:
                self.groups[g.cid.upper()] = g
        
        # Brands (by code and name as fallback)
        self.brands = {}
        for b in self.env['xnk.brand'].search([]):
            # Index by code if available
            if hasattr(b, 'code') and b.code:
                self.brands[b.code.upper()] = b
            # Also index by name for fallback
            if b.name:
                self.brands[b.name.upper()] = b
        
        # Countries (by code)
        self.countries = {}
        for c in self.env['xnk.country'].search([]):
            if c.code:
                self.countries[c.code.upper()] = c
        
        # Currencies (by name/code)
        self.currencies = {}
        for curr in self.env['res.currency'].search([]):
            if curr.name:
                self.currencies[curr.name.upper()] = curr
        
        # Warranties (by code)
        self.warranties = {}
        for w in self.env['xnk.warranty'].search([]):
            if hasattr(w, 'code') and w.code:
                self.warranties[w.code.upper()] = w
            # Also index by name for fallback
            if w.name:
                self.warranties[w.name.upper()] = w
        
        # Suppliers (by ref, which is the actual column in res.partner)
        self.suppliers = {}
        partners = self.env['res.partner'].search([('supplier_rank', '>', 0)])
        for p in partners:
            # Index by ref field (this is what res.partner uses)
            if hasattr(p, 'ref') and p.ref:
                self.suppliers[str(p.ref).strip().upper()] = p
            # Also index by name for fallback
            if p.name:
                self.suppliers[p.name.upper()] = p
        
        # Lens-specific master data
        self.designs = {}
        for d in self.env['product.design'].search([]):
            if d.cid:
                self.designs[d.cid.upper()] = d
        
        self.materials = {}
        for m in self.env['product.material'].search([]):
            if m.cid:
                self.materials[m.cid.upper()] = m
        
        self.uvs = {}
        for u in self.env['product.uv'].search([]):
            if u.cid:
                self.uvs[u.cid.upper()] = u
        
        self.coatings = {}
        for c in self.env['product.coating'].search([]):
            if c.cid:
                self.coatings[c.cid.upper()] = c
        
        self.colors = {}  # product.cl  
        for cl in self.env['product.cl'].search([]):
            if cl.cid:
                self.colors[cl.cid.upper()] = cl
        
        self.lens_indexes = {}
        for li in self.env['product.lens.index'].search([]):
            if li.cid:
                self.lens_indexes[li.cid.upper()] = li
        
        # OPT-specific master data
        self.frames = {}
        for f in self.env['product.frame'].search([]):
            if f.cid:
                self.frames[f.cid.upper()] = f
        
        self.frame_types = {}
        for ft in self.env['product.frame.type'].search([]):
            if ft.cid:
                self.frame_types[ft.cid.upper()] = ft
        
        self.shapes = {}
        for s in self.env['product.shape'].search([]):
            if s.cid:
                self.shapes[s.cid.upper()] = s
        
        self.ves = {}
        for v in self.env['product.ve'].search([]):
            if v.cid:
                self.ves[v.cid.upper()] = v
        
        self.temples = {}
        for t in self.env['product.temple'].search([]):
            if t.cid:
                self.temples[t.cid.upper()] = t
    
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
        
        key = str(cid).strip().upper()
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
        """Get country by code"""
        return self.get(self.countries, code)
    
    def get_currency(self, name):
        """Get currency by name"""
        return self.get(self.currencies, name)
    
    def get_warranty(self, cid):
        """Get warranty by CID"""
        return self.get(self.warranties, cid)
    
    def get_supplier(self, cid_or_name):
        """Get supplier by CID or name"""
        return self.get(self.suppliers, cid_or_name)
    
    def get_design(self, cid):
        """Get design by CID"""
        return self.get(self.designs, cid)
    
    def get_material(self, cid):
        """Get material by CID"""
        return self.get(self.materials, cid)
    
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
