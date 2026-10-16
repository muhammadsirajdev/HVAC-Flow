"""Background jobs (APScheduler, inside the app): the inbox poll (Run B), the Slack status
check (Run C) and the daily reminders (Run D), each when enabled in .env. One instance of a job at a time: a slow run is never
overlapped by the next one."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import get_settings

log = logging.getLogger(__name__)


def start() -> BackgroundScheduler:
    s = get_settings()
    scheduler = BackgroundScheduler(timezone=s.business_tz)
    if s.email_poll_enabled:
        from backend.graphs.run_b_email.poller import poll_once
        scheduler.add_job(poll_once, "interval", seconds=s.email_poll_seconds, id="email_poll",
                          max_instances=1, coalesce=True)
        log.info("email poll every %ss", s.email_poll_seconds)
    if s.slack_status_enabled:
        from backend.graphs.run_c_slack_status.graph import run_once
        scheduler.add_job(run_once, "interval", hours=s.slack_status_hours, id="slack_status",
                          max_instances=1, coalesce=True)
        log.info("Slack status check every %sh", s.slack_status_hours)
    if s.reminders_enabled:
        from backend.graphs.run_d_reminders.graph import run_once as send_reminders
        scheduler.add_job(send_reminders, "cron", hour=s.reminder_hour, id="reminders",
                          max_instances=1, coalesce=True)
        log.info("reminders daily at %s:00", s.reminder_hour)
    scheduler.start()
    return scheduler
