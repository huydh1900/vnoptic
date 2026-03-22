"""
Code Structure (13 characters):
    [XX][XXX][XXX][XXXXX]
    │   │    │    └─────── 5 chars: Numeric Sequence (00001, 00002...)
    │   │    └──────────── 3 chars: Lens Index CID
    │   └───────────────── 3 chars: Brand ID
    └───────────────────── 2 chars: Group ID

Sequence Logic:
    ir.sequence provides specific formatting:
    - padding: 5
    - number_increment: 1
    
    Example:
        1 -> 00001
        9 -> 00009
        99 -> 00099
"""

import logging

_logger = logging.getLogger(__name__)

SEQUENCE_CODE_PREFIX = "vnop_product"


def _base36_encode(number):
    """
    Convert integer to Base36 string (0-9, A-Z)
    Used to match RS system format: 000BL, 000N1, etc.
    """
    if number == 0:
        return '00000'
    
    chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    result = ''
    while number:
        result = chars[number % 36] + result
        number //= 36
    return result.rjust(5, '0')


def _get_prefix_components(env, categ_id, brand_id, lens_index_id, lens_index_cache=None):
    """
    Helper to generate prefix string from category, brand, and lens index
    
    Returns: (categ_part, brand_part, index_part)
    - categ_part: 2 digits from category.code (e.g., '06', '27', '20')
    - brand_part: 3 digits from brand.code or brand.id (e.g., '003', '004')
    - index_part: 3 digits from lens_index.cid (e.g., '167')
    """
    # Category Part (2 digits)
    categ_part = '00'
    if categ_id:
        category = env['product.category'].browse(categ_id)
        if category.code:
            categ_part = category.code[:2].ljust(2, '0')
    
    # Brand Part (3 digits)
    brand_part = '000'
    if brand_id:
        brand = env['product.brand'].browse(brand_id)
        if brand.code:
            # Use brand.code if available
            brand_part = brand.code[:3].zfill(3)
        else:
            # Fallback to brand ID
            brand_part = f"{brand_id:03d}"
    
    # Index Part (3 digits) - only for lens products
    index_part = "000"
    if lens_index_id:
        if lens_index_cache and lens_index_id in lens_index_cache:
            cid = lens_index_cache[lens_index_id]
        else:
            lens_index = env['product.lens.index'].browse(lens_index_id)
            cid = lens_index.cid if lens_index and lens_index.cid else "000"
        index_part = cid[:3].ljust(3, '0')
    
    return categ_part, brand_part, index_part

def _ensure_sequence_exists(env, prefix):
    """
    Ensure an ir.sequence exists for the given prefix.
    If not, initialize it by finding the max existing numeric suffix.
    """
    seq_code = f"{SEQUENCE_CODE_PREFIX}.{prefix}"
    # Search by code
    sequence = env['ir.sequence'].search([('code', '=', seq_code)], limit=1)
    
    if sequence:
        return sequence
    
    # Create new sequence
    # Find max existing number for this prefix from existing products
    _logger.info(f"Sequence for prefix {prefix} not found. Searching existing products to initialize...")
    
    ProductTemplate = env['product.template']
    domain = [('default_code', 'like', f'{prefix}%')]
    
    existing_codes = ProductTemplate.search(domain).mapped('default_code')
    
    max_num = 0
    
    for code in existing_codes:
        if not code or len(code) != len(prefix) + 5: # Expecting prefix + 5 digits
            continue
        if not code.startswith(prefix):
            continue
            
        suffix = code[len(prefix):]
        if suffix.isdigit():
            num = int(suffix)
            if num > max_num:
                max_num = num
    
    next_number = max_num + 1
    _logger.info(f"Initializing numeric sequence {seq_code} starting at {next_number} (Found max: {max_num})")
    
    return env['ir.sequence'].create({
        'name': f'Product Auto Sequence {prefix}',
        'code': seq_code,
        'prefix': '',     # We prepend the prefix manually in the caller, or handled by logic
        'suffix': '',
        'padding': 5,     # Requirement: 5 chars padding (00001)
        'number_next': next_number,
        'number_increment': 1,
        'implementation': 'standard',
        'company_id': False,
    })

def generate_product_code(env, categ_id, brand_id, lens_index_id):
    """
    Generate a single product code using Base36 encoded sequence
    
    Args:
        categ_id: product.category ID
        brand_id: product.brand ID  
        lens_index_id: product.lens.index ID (optional, only for lens)
    
    Returns:
        13-character product code (e.g., '06004167000BL')
    """
    categ_part, brand_part, index_part = _get_prefix_components(env, categ_id, brand_id, lens_index_id)
    prefix = f"{categ_part}{brand_part}{index_part}"
    
    sequence = _ensure_sequence_exists(env, prefix)
    
    # Get next number from sequence (returns formatted string like '00001')
    # We need to extract the integer value
    seq_str = sequence.next_by_id()
    seq_number = int(seq_str) if seq_str.isdigit() else 1
    
    # Convert to Base36 (matches RS format: 000BL, 000N1, etc.)
    seq_suffix = _base36_encode(seq_number)
    
    final_code = f"{prefix}{seq_suffix}"
    _logger.info(f"Generated product code {final_code}")
    
    return final_code

def generate_product_codes_batch(env, code_requests):
    """
    Generate product codes for multiple products at once.
    code_requests: list of tuples (categ_id, brand_id, lens_index_id)
    """
    if not code_requests:
        return []
    
    # Cache lens index CIDs
    lens_index_cache = {}
    unique_lens_ids = set(req[2] for req in code_requests if req[2])
    if unique_lens_ids:
        lens_indexes = env['product.lens.index'].browse(list(unique_lens_ids))
        for li in lens_indexes:
            lens_index_cache[li.id] = li.cid[:3].ljust(3, '0') if li.cid else '000'
    
    # 1. Prepare all prefixes
    prefixes = []
    for categ_id, brand_id, lens_index_id in code_requests:
        c, b, i = _get_prefix_components(env, categ_id, brand_id, lens_index_id, lens_index_cache)
        prefixes.append(f"{c}{b}{i}")
    
    # 2. Ensure sequences exist
    unique_prefixes = set(prefixes)
    sequences = {}
    for prefix in unique_prefixes:
        sequences[prefix] = _ensure_sequence_exists(env, prefix)
    
    # 3. Generate codes with Base36 encoding
    results = []
    for prefix in prefixes:
        seq = sequences[prefix]
        # Get next number and convert to Base36
        seq_str = seq.next_by_id()
        seq_number = int(seq_str) if seq_str.isdigit() else 1
        seq_suffix = _base36_encode(seq_number)
        results.append(f"{prefix}{seq_suffix}")
        
    return results
