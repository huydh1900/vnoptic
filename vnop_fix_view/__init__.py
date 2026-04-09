import logging

_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    """Delete all views belonging to vnop_* modules from database,
    forcing Odoo to recreate them from XML files and clearing any
    stale references to removed fields/actions."""
    env.cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE model = 'ir.ui.view'
              AND module LIKE 'vnop_%'
        )
    """)
    view_count = env.cr.rowcount

    env.cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.ui.view'
          AND module LIKE 'vnop_%'
    """)
    data_count = env.cr.rowcount

    if view_count:
        _logger.info(
            "vnop_fix_view: deleted %d view(s) and %d ir_model_data record(s) from vnop_* modules",
            view_count, data_count,
        )
