"""Section 10.2 — Timetable -> Session Instance generation.

Meant to run once a day (e.g. via host cron calling `flask generate-sessions`,
or APScheduler). Decouples the recurring timetable template from the
day-to-day operational record.
"""
from datetime import datetime, timedelta
from flask import current_app
from app.extensions import db
from app.models import TimetableSession, SessionInstance, Term

WEEKDAY_MAP = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: None, 6: None}


def run(for_date=None):
    for_date = for_date or datetime.utcnow().date()
    day_code = WEEKDAY_MAP.get(for_date.weekday())
    if not day_code:
        return 0  # weekend, nothing to generate

    current_term = Term.query.filter_by(is_current=True).first()
    if not current_term:
        return 0

    grace_minutes = current_app.config.get("GRACE_PERIOD_MINUTES", 20)

    sessions_today = TimetableSession.query.filter_by(
        term_id=current_term.id, day_of_week=day_code
    ).all()

    created = 0
    for ts in sessions_today:
        exists = SessionInstance.query.filter_by(
            timetable_session_id=ts.id, session_date=for_date
        ).first()
        if exists:
            continue

        grace_deadline = datetime.combine(for_date, ts.end_time) + timedelta(minutes=grace_minutes)
        instance = SessionInstance(
            timetable_session_id=ts.id,
            session_date=for_date,
            status=SessionInstance.STATUS_SCHEDULED,
            grace_deadline=grace_deadline,
        )
        db.session.add(instance)
        created += 1

    db.session.commit()
    return created
