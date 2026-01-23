# -*- coding: utf-8 -*-
"""
Product Code Generation Utility

This module provides utility functions for generating automatic product codes
following the VNOPTIC naming convention:

Code Structure (13 characters):
    [XX][XXX][XXX][XXXXX]
    │   │    │    └─────── 5 chars: Auto-increment (0-9, A-Z pattern)
    │   │    └──────────── 3 chars: Lens Index CID
    │   └───────────────── 3 chars: Brand ID
    └───────────────────── 2 chars: Group ID

Auto-increment Pattern:
    00000 → 00009 → 0000A → 0000Z →
    00010 → 00019 → 0001A → 0001Z →
    00020 → 00029 → 0002A → 0002Z →
    ...
"""

import logging

_logger = logging.getLogger(__name__)


def parse_sequence(seq_str):

    if not seq_str or len(seq_str) != 5:
        return (0, False, 0)
    
    last_char = seq_str[-1]
    
    if last_char.isalpha():
        group_str = seq_str[:4].lstrip('0') or '0'
        group = int(group_str)
        return (group, True, last_char.upper())
    else:
        group_str = seq_str[:3].lstrip('0') or '0'
        group = int(group_str)
        digit = int(last_char)
        return (group, False, digit)


def format_sequence(group, is_letter, value):

    if is_letter:
        # Format: 0000A, 0001B, 0099Z
        return f"{group:04d}{value}"
    else:
        # Format: 00001, 00019, 00999
        return f"{group:03d}{value:01d}"


def get_next_sequence(current_seq):

    group, is_letter, value = parse_sequence(current_seq)
    
    if is_letter:
        # Currently on a letter
        if value == 'Z':
            # After Z, go to next group's first digit (starting from 0)
            next_group = group + 1
            return format_sequence(next_group, False, 0)
        else:
            # Next letter in same group
            next_letter = chr(ord(value) + 1)
            return format_sequence(group, True, next_letter)
    else:
        # Currently on a digit
        if value == 9:
            # After 9, go to first letter of same group
            return format_sequence(group, True, 'A')
        else:
            # Next digit in same group
            return format_sequence(group, False, value + 1)


def generate_product_code(env, group_id, brand_id, lens_index_id):

    if group_id:
        group_part = f"{group_id:02d}"
    else:
        group_part = "00"
    
    # Format brand ID (3 digits)
    if brand_id:
        brand_part = f"{brand_id:03d}"
    else:
        brand_part = "000"
    
    # Format lens index CID (3 characters)
    if lens_index_id:
        lens_index = env['product.lens.index'].browse(lens_index_id)
        if lens_index and lens_index.cid:
            # Take first 3 characters of CID
            index_part = (lens_index.cid[:3]).ljust(3, '0')
        else:
            index_part = "000"
    else:
        index_part = "000"
    
    # Create prefix (first 8 characters)
    prefix = f"{group_part}{brand_part}{index_part}"
    
    # Find the latest sequence with this prefix
    ProductTemplate = env['product.template']
    
    # Search for existing products with this prefix
    existing_codes = ProductTemplate.search([
        ('default_code', 'like', f'{prefix}%')
    ]).mapped('default_code')
    
    # Filter to exact prefix matches and extract sequences
    sequences = []
    for code in existing_codes:
        if code and len(code) >= 13 and code[:8] == prefix:
            seq = code[8:13]
            sequences.append(seq)
    
    # Find the highest sequence
    if sequences:
        # Sort sequences to find the latest
        sequences.sort()
        latest_seq = sequences[-1]
        next_seq = get_next_sequence(latest_seq)
    else:
        # No existing codes, start with 00000
        next_seq = "00000"
    
    # Generate final code
    final_code = f"{prefix}{next_seq}"
    
    _logger.info(f"Generated product code: {final_code} (prefix: {prefix}, sequence: {next_seq})")
    
    return final_code


def generate_product_codes_batch(env, code_requests):
    """
    Generate product codes for multiple products at once.
    
    This is much more efficient than calling generate_product_code() in a loop
    because it:
    - Queries the database once per unique prefix instead of once per product
    - Pre-calculates all sequences before any products are created
    
    Args:
        env: Odoo environment
        code_requests: List of tuples (group_id, brand_id, lens_index_id)
    
    Returns:
        List of generated codes in the same order as code_requests
    """
    if not code_requests:
        return []
    
    # Cache lens index CIDs to avoid repeated lookups
    lens_index_cache = {}
    unique_lens_ids = set(req[2] for req in code_requests if req[2])
    if unique_lens_ids:
        lens_indexes = env['product.lens.index'].browse(list(unique_lens_ids))
        for li in lens_indexes:
            lens_index_cache[li.id] = li.cid[:3].ljust(3, '0') if li.cid else '000'
    
    # Build prefixes for all requests
    prefix_map = {}  # prefix -> list of request indices
    for idx, (group_id, brand_id, lens_index_id) in enumerate(code_requests):
        # Build prefix
        group_part = f"{group_id:02d}" if group_id else "00"
        brand_part = f"{brand_id:03d}" if brand_id else "000"
        index_part = lens_index_cache.get(lens_index_id, "000") if lens_index_id else "000"
        prefix = f"{group_part}{brand_part}{index_part}"
        
        if prefix not in prefix_map:
            prefix_map[prefix] = []
        prefix_map[prefix].append(idx)
    
    # Query existing codes for all prefixes at once
    ProductTemplate = env['product.template']
    all_prefixes = list(prefix_map.keys())
    
    # Build OR domain for all prefixes
    domains = [('default_code', '=like', f'{prefix}%') for prefix in all_prefixes]
    if len(domains) == 1:
        combined_domain = domains[0]
    else:
        combined_domain = ['|'] * (len(domains) - 1) + domains
    
    existing_codes = ProductTemplate.search([combined_domain]).mapped('default_code')
    
    # Group existing codes by prefix
    prefix_sequences = {prefix: [] for prefix in all_prefixes}
    for code in existing_codes:
        if code and len(code) >= 13:
            code_prefix = code[:8]
            if code_prefix in prefix_sequences:
                seq = code[8:13]
                prefix_sequences[code_prefix].append(seq)
    
    # Generate codes for each request
    result_codes = [None] * len(code_requests)
    
    for prefix, indices in prefix_map.items():
        # Get sequences for this prefix
        sequences = prefix_sequences[prefix]
        
        # Find starting sequence
        if sequences:
            sequences.sort()
            current_seq = sequences[-1]
        else:
            current_seq = None
        
        # Generate codes for all products with this prefix
        for idx in indices:
            if current_seq is None:
                next_seq = "00000"
            else:
                next_seq = get_next_sequence(current_seq)
            
            result_codes[idx] = f"{prefix}{next_seq}"
            current_seq = next_seq
    
    _logger.info(f"Batch generated {len(result_codes)} product codes for {len(prefix_map)} unique prefixes")
    
    return result_codes
