# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class QueueJob(models.Model):
    _inherit = "queue.job"

    def action_open_import_from_test_queue(self):
        self.ensure_one()
        if self.model_name != "product.import.queue.session" or self.method_name != "_run_test_queue_job":
            raise UserError(_("This job is not a product import test job."))
        if self.state not in ("done", "failed"):
            raise UserError(_("The test job is not completed yet."))

        session = self.records
        if not session:
            try:
                session_id = self.args[0]
            except Exception:
                session_id = False
            session = self.env["product.import.queue.session"].browse(session_id)

        if not session.exists():
            raise UserError(_("Import test session not found."))
        if session.requested_by and session.requested_by != self.env.user:
            raise UserError(_("You are not allowed to reopen this import session."))
        if session.job_type != "test" or session.state not in ("done", "error"):
            raise UserError(_("Only completed test sessions can be reopened for import."))

        return session.action_open_import_wizard()
