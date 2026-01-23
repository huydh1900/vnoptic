from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    eng_name = fields.Char("English Name")
    trade_name = fields.Char("Trade Name")

    # ==================== PRICE FIELDS (moved from xnk_intergration) ====================
    x_ws_price = fields.Float(
        'Wholesale Price',
        digits='Product Price',
        help="Wholesale price"
    )
    x_ct_price = fields.Float(
        'Cost Price',
        digits='Product Price',
        help="Cost price"
    )
    x_or_price = fields.Float(
        'Original Price',
        digits='Product Price',
        help="Original price from supplier"
    )
    x_ws_price_min = fields.Float(
        'Min Wholesale Price',
        digits='Product Price',
        help="Minimum wholesale price"
    )
    x_ws_price_max = fields.Float(
        'Max Wholesale Price',
        digits='Product Price',
        help="Maximum wholesale price"
    )
    x_tax_percent = fields.Float(
        'Tax Percentage',
        digits=(5, 2),
        help="Tax rate percentage"
    )

    # ==================== INFO FIELDS (moved from xnk_intergration) ====================
    x_eng_name = fields.Char(
        'English Name (XNK)',
        help="Product name in English"
    )
    x_trade_name = fields.Char(
        'Trade Name (XNK)',
        help="Commercial trade name"
    )
    x_note_long = fields.Text(
        'Long Description',
        help="Detailed product description"
    )
    x_status_name = fields.Char(
        'Product Status',
        help="Current product status from API"
    )
    x_cid_ncc = fields.Char(
        'Supplier Code (NCC)',
        help="Supplier product code"
    )
    x_accessory_total = fields.Integer(
        'Total Accessories',
        default=0,
        help="Number of accessories included"
    )
    x_currency_zone_code = fields.Char(
        'Currency Zone Code',
        help="Currency zone code from API"
    )
    x_group_type_name = fields.Char(
        'Product Group Type',
        help="Product group type classification"
    )

    access_total = fields.Integer("Accessory Total")
    cid_ncc = fields.Char("Supplier code")
    unit = fields.Char("Unit", default="Chiếc")
    description = fields.Text("Description")
    uses = fields.Text("Uses")
    guide = fields.Text("Guide")
    warning = fields.Text("Warning")
    preserve = fields.Text('Preserve')

    supplier_id = fields.Many2one('res.partner', string='Supplier')
    group_id = fields.Many2one('product.group', string='Product Group')
    status_group_id = fields.Many2one('product.status', string='Status Product Group')
    
    # Multiple warranty fields
    warranty_id = fields.Many2one('xnk.warranty', 'Warranty')
    warranty_detail_id = fields.Many2one('xnk.warranty', 'Warranty Detail')
    warranty_retail_id = fields.Many2one('xnk.warranty', 'Warranty Retail')
    warranty_supplier_id = fields.Many2one('xnk.warranty', 'Warranty Supplier')
    
    # Currency selection for foreign currency products
    currency_selection = fields.Selection([
        ('vnd', 'VND'),
        ('usd', 'USD'),
        ('japan', 'Japan (YÊN)'),
        ('china', 'China (TỆ)')
    ], string='Currency Selection', default='vnd')
    currency_zone_id = fields.Many2one('res.currency', 'Currency Zone')
    x_currency_zone_value = fields.Float('Exchange Rate', default=1.0, digits=(12, 2))
    
    status_product_id = fields.Many2one('product.status', 'Status Product')
    brand_id = fields.Many2one('xnk.brand', 'Brand', index=True, tracking=True)
    country_id = fields.Many2one('xnk.country', 'Country of Origin')

    product_type = fields.Selection([
        ('lens', 'Lens'),
        ('opt', 'Optical Product'),
        ('accessory', 'Accessory')
    ], string='Product Type', default='lens')

    lens_ids = fields.One2many('product.lens', 'product_tmpl_id', 'Lens Details')
    opt_ids = fields.One2many('product.opt', 'product_tmpl_id', 'Optical Details')
    
    # Computed fields for tree view display
    # Lens fields
    lens_sph = fields.Char('SPH', compute='_compute_lens_info', store=False, readonly=True)
    lens_cyl = fields.Char('CYL', compute='_compute_lens_info', store=False, readonly=True)
    lens_index_name = fields.Char('Index', compute='_compute_lens_info', store=False, readonly=True)
    lens_add = fields.Char('Add', compute='_compute_lens_info', store=False, readonly=True)
    
    # Opt fields
    opt_model = fields.Char('Model', compute='_compute_opt_info', store=False, readonly=True)
    opt_color = fields.Char('Color', compute='_compute_opt_info', store=False, readonly=True)
    opt_frame_type = fields.Char('Frame Type', compute='_compute_opt_info', store=False, readonly=True)
    opt_shape = fields.Char('Shape', compute='_compute_opt_info', store=False, readonly=True)
    
    @api.depends('lens_ids', 'lens_ids.sph', 'lens_ids.cyl', 'lens_ids.index_id', 'lens_ids.len_add', 'product_type')
    def _compute_lens_info(self):
        for record in self:
            if record.product_type == 'lens' and record.lens_ids:
                lens = record.lens_ids[0]
                record.lens_sph = lens.sph or ''
                record.lens_cyl = lens.cyl or ''
                record.lens_index_name = lens.index_id.name if lens.index_id else ''
                record.lens_add = lens.len_add or ''
            else:
                record.lens_sph = ''
                record.lens_cyl = ''
                record.lens_index_name = ''
                record.lens_add = ''
    
    @api.depends('opt_ids', 'opt_ids.model', 'opt_ids.color', 'opt_ids.frame_type_id', 'opt_ids.shape_id', 'product_type')
    def _compute_opt_info(self):
        for record in self:
            if record.product_type == 'opt' and record.opt_ids:
                opt = record.opt_ids[0]
                record.opt_model = opt.model or ''
                record.opt_color = opt.color or ''
                record.opt_frame_type = opt.frame_type_id.name if opt.frame_type_id else ''
                record.opt_shape = opt.shape_id.name if opt.shape_id else ''
            else:
                record.opt_model = ''
                record.opt_color = ''
                record.opt_frame_type = ''
                record.opt_shape = ''
    
    @api.onchange('currency_selection')
    def _onchange_currency_selection(self):
        """Set currency_zone_id based on selection and suggest exchange rate"""
        if self.currency_selection:
            currency_map = {
                'vnd': 'VND',
                'usd': 'USD',
                'japan': 'JPY',
                'china': 'CNY'
            }
            currency_code = currency_map.get(self.currency_selection)
            if currency_code:
                currency = self.env['res.currency'].sudo().search([('name', '=', currency_code)], limit=1)
                if currency:
                    self.currency_zone_id = currency.id
                    if self.currency_selection == 'vnd':
                        self.x_currency_zone_value = 1.0

    @api.onchange('group_id', 'brand_id')
    def _onchange_generate_product_code(self):
        """Auto-generate product code when group or brand changes"""
        from odoo.addons.vnoptic_product import utils as vnoptic_utils
        
        if self.group_id or self.brand_id:
            # Get lens_index_id from lens_ids if product_type is lens
            lens_index_id = False
            if self.product_type == 'lens' and self.lens_ids:
                lens_index_id = self.lens_ids[0].index_id.id if self.lens_ids[0].index_id else False
            
            code = vnoptic_utils.product_code_utils.generate_product_code(
                self.env,
                self.group_id.id if self.group_id else False,
                self.brand_id.id if self.brand_id else False,
                lens_index_id
            )
            self.default_code = code

    @api.model
    def create(self, vals):
        product_type = vals.get('product_type', 'lens')

        if product_type != 'lens':
            if 'lens_ids' in vals:
                del vals['lens_ids']

        if product_type != 'opt':
            if 'opt_ids' in vals:
                del vals['opt_ids']

        product = super().create(vals)
        
        # Auto-create lens/opt record if needed
        if product_type == 'lens' and not product.lens_ids:
            self.env['product.lens'].create({'product_tmpl_id': product.id})
        elif product_type == 'opt' and not product.opt_ids:
            self.env['product.opt'].create({'product_tmpl_id': product.id})
        
        return product

    def write(self, vals):
        product_type = vals.get('product_type') or self.product_type

        if 'product_type' in vals:
            if vals['product_type'] != 'lens':
                self.lens_ids.unlink()
                if 'lens_ids' in vals:
                    del vals['lens_ids']

            if vals['product_type'] != 'opt':
                self.opt_ids.unlink()
                if 'opt_ids' in vals:
                    del vals['opt_ids']

        return super().write(vals)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        many2one_fields = [
            'supplier_id', 'group_id', 'status_group_id', 'warranty_id',
            'currency_zone_id', 'status_product_id', 'brand_id', 'country_id'
        ]
        
        for field in many2one_fields:
            if field in fields_list and field not in res:
                res[field] = False
        
        return res

    def action_fix_product_type(self):
        for product in self:
            if product.product_type and product.product_type != 'lens':
                continue
                
            if product.lens_ids:
                product.product_type = 'lens'
            elif product.opt_ids:
                product.product_type = 'opt'
            elif product.group_id:
                group_name = product.group_id.name
                if 'Mắt' in group_name or 'Lens' in group_name or 'lens' in group_name:
                    product.product_type = 'lens'
                elif 'Gọng' in group_name or 'Optical' in group_name or 'opt' in group_name.lower():
                    product.product_type = 'opt'
                else:
                    product.product_type = 'accessory'
            else:
                if not product.product_type:
                    product.product_type = 'accessory'
        
        return True

    @api.model
    def cron_fix_all_product_types(self):
        products = self.search([])
        products.action_fix_product_type()
        return True
