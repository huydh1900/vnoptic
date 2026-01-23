from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    # Drop columns if they exist
    cr.execute("""
        ALTER TABLE product_template 
        DROP COLUMN IF EXISTS cid CASCADE
    """)
    
    cr.commit()  