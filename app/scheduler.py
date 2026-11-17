"""Tiny in-process scheduler that runs the stock-check scan periodically."""

import logging
import os
import threading

log = logging.getLogger(__name__)

_started = False


def start_alert_scheduler(app):

    global _started

    if _started or not app.config.get("ALERT_SCHEDULER") or app.config.get("TESTING"):
        return

    # With the debug reloader, only start in the child process that serves requests.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    _started = True
    interval = max(app.config.get("ALERT_INTERVAL_MINUTES", 60), 1) * 60

    def job():
        with app.app_context():
            try:
                from app.services.check_service import CheckService
                summary = CheckService.run()
                log.info("Stock-check scan: %s", summary)
            except Exception:  # keep the scheduler alive
                log.exception("Stock-check scan failed")
                from app.extensions import db
                db.session.rollback()

        timer = threading.Timer(interval, job)
        timer.daemon = True
        timer.start()

    first = threading.Timer(5, job)
    first.daemon = True
    first.start()
