"""Background jobs (APScheduler, inside the app): the inbox poll (Run B).

Started by main.py when EMAIL_POLL_ENABLED=true. One job instance at a time: a slow poll is
never overlapped by the next one.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import get_settings

log = logging.getLogger(__name__)


def start() -> BackgroundScheduler:
    from backend.graphs.run_b_email.poller import poll_once

    s = get_settings()
    scheduler = BackgroundScheduler(timezone=s.business_tz)
    scheduler.add_job(poll_once, "interval", seconds=s.email_poll_seconds, id="email_poll",
                      max_instances=1, coalesce=True)
    scheduler.start()
    log.info("email poll every %ss", s.email_poll_seconds)
    return scheduler
