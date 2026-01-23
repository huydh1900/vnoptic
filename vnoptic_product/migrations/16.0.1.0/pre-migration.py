"""
Migration script to handle field changes in vnoptic_product module
This version reverts fields back to Many2one format
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Handle field changes - drop old Char columns if they exist
    since we're reverting to Many2one fields
    """
    _logger.info("=" * 80)
    _logger.info(f"Starting migration from version {version}")
    
    # Check if product_design table exists and has Char columns
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'product_design' 
        AND column_name IN ('frame', 'frame_type', 'shape', 've', 'temple')
        AND data_type = 'character varying';
    """)
    char_columns = [row[0] for row in cr.fetchall()]
    
    if char_columns:
        _logger.info(f"Found Char columns to drop in product_design: {char_columns}")
        for col in char_columns:
            _logger.info(f"Dropping column: {col}")
            cr.execute(f"ALTER TABLE product_design DROP COLUMN IF EXISTS {col};")
    
    # Check if product_opt table has Char columns
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'product_opt' 
        AND column_name IN ('frame', 'frame_type', 'shape', 've', 'temple', 'color_front', 'color_temple')
        AND data_type = 'character varying';
    """)
    opt_char_columns = [row[0] for row in cr.fetchall()]
    
    if opt_char_columns:
        _logger.info(f"Found Char columns to drop in product_opt: {opt_char_columns}")
        for col in opt_char_columns:
            _logger.info(f"Dropping column: {col}")
            cr.execute(f"ALTER TABLE product_opt DROP COLUMN IF EXISTS {col};")
    
    _logger.info("Migration completed successfully")
    _logger.info("=" * 80)
