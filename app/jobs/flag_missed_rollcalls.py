"""Section 10.3 — Missed Roll Call Auto-Flagging.

Meant to run every ~15 minutes throughout the school day (host cron calling
`flask flag-missed-rollcalls`, or APScheduler).
"""
from datetime import datetime
from app.extensions import db
from app.models import SessionInstance


def run(now=None):
    now = now or datetime.utcnow()

    overdue = SessionInstance.query.filter(
        SessionInstance.status == SessionInstance.STATUS_SCHEDULED,
        SessionInstance.grace_deadline < now,
    ).all()

    for instance in overdue:
        instance.status = SessionInstance.STATUS_FLAGGED

    db.session.commit()
    return len(overdue)
