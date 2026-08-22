from datetime import timedelta
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models import (
    User, AttendanceRecord, SessionInstance, TimetableSession, SchoolClass, Student
)
from app.utils import current_term

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.before_request
@login_required
def restrict_to_logged_in():
    pass


@dashboard_bp.route("/attendance")
def attendance_series():
    """Section 10.8 — one reusable, parameterised aggregation endpoint that
    feeds every Chart.js visualisation across every dashboard.

    Query params:
      level: lesson|daily|weekly|monthly|termly (bucket size)
      scope: class|subject|student|teacher
    """
    level = request.args.get("level", "daily")
    term = current_term()

    query = AttendanceRecord.query.join(SessionInstance).join(TimetableSession)
    if term:
        query = query.filter(TimetableSession.term_id == term.id)

    # Teachers only ever see their own sessions on this endpoint
    if current_user.role == User.ROLE_TEACHER:
        query = query.filter(TimetableSession.teacher_id == current_user.id)

    records = query.all()

    buckets = {}
    for r in records:
        d = r.session_instance.session_date
        if level == "weekly":
            key = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]}"
        elif level == "monthly":
            key = d.strftime("%Y-%m")
        elif level == "termly":
            key = term.name if term else "Term"
        else:
            key = d.isoformat()
        buckets.setdefault(key, {"present": 0, "total": 0})
        buckets[key]["total"] += 1
        if r.status in ("present", "late"):
            buckets[key]["present"] += 1

    labels = sorted(buckets.keys())
    values = [
        round((buckets[k]["present"] / buckets[k]["total"]) * 100, 1) if buckets[k]["total"] else 0
        for k in labels
    ]

    return jsonify({"labels": labels, "values": values})


@dashboard_bp.route("/attendance-by-class")
def attendance_by_class():
    term = current_term()
    classes = SchoolClass.query.filter_by(school_id=current_user.school_id).all()
    labels, values = [], []
    for c in classes:
        students = Student.query.filter_by(class_id=c.id, is_active=True).all()
        pcts = [s.attendance_percentage(term_id=term.id if term else None) for s in students]
        pcts = [p for p in pcts if p is not None]
        if pcts:
            labels.append(c.display_name)
            values.append(round(sum(pcts) / len(pcts), 1))
    return jsonify({"labels": labels, "values": values})
