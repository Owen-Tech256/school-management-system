import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    User, TimetableSession, SessionInstance, StudentSubjectEnrollment,
    AttendanceRecord, AttendanceAuditLog, Student, RollCallDraft
)
from app.utils import roles_required, current_term
from app.services.audit_service import log_attendance_change

teacher_bp = Blueprint("teacher", __name__)


@teacher_bp.before_request
@login_required
@roles_required(User.ROLE_TEACHER)
def restrict_to_teachers():
    pass


@teacher_bp.route("/dashboard")
def dashboard():
    today = datetime.utcnow().date()
    sessions_today = (
        SessionInstance.query.join(TimetableSession)
        .filter(TimetableSession.teacher_id == current_user.id, SessionInstance.session_date == today)
        .order_by(TimetableSession.period_number)
        .all()
    )

    term = current_term()
    missed_count = 0
    if term:
        missed_count = (
            SessionInstance.query.join(TimetableSession)
            .filter(
                TimetableSession.teacher_id == current_user.id,
                TimetableSession.term_id == term.id,
                SessionInstance.status == SessionInstance.STATUS_FLAGGED,
            ).count()
        )

    return render_template(
        "teacher/dashboard.html", sessions_today=sessions_today, missed_count=missed_count, today=today
    )


@teacher_bp.route("/my-classes")
def my_classes():
    term = current_term()
    assignments = TimetableSession.query.filter_by(teacher_id=current_user.id)
    if term:
        assignments = assignments.filter_by(term_id=term.id)
    assignments = assignments.all()

    stats = []
    seen = set()
    for a in assignments:
        key = (a.class_id, a.subject_id)
        if key in seen:
            continue
        seen.add(key)
        records = (
            AttendanceRecord.query.join(SessionInstance).join(TimetableSession)
            .filter(TimetableSession.class_id == a.class_id, TimetableSession.subject_id == a.subject_id,
                    TimetableSession.teacher_id == current_user.id)
            .all()
        )
        pct = None
        if records:
            present_like = sum(1 for r in records if r.status in ("present", "late"))
            pct = round((present_like / len(records)) * 100, 1)
        stats.append((a.school_class, a.subject, pct, len(records)))

    return render_template("teacher/my_classes.html", stats=stats)


@teacher_bp.route("/sessions/<int:session_instance_id>/rollcall", methods=["GET", "POST"])
def rollcall(session_instance_id):
    instance = SessionInstance.query.get_or_404(session_instance_id)
    ts = instance.timetable_session
    if ts.teacher_id != current_user.id:
        abort(403)

    term = current_term()
    enrollments = (
        StudentSubjectEnrollment.query.filter_by(subject_id=ts.subject_id, term_id=ts.term_id)
        .join(Student).filter(Student.class_id == ts.class_id, Student.is_active == True)
        .order_by(Student.full_name)
        .all()
    )
    roster = [e.student for e in enrollments]

    existing_records = {
        r.student_id: r for r in AttendanceRecord.query.filter_by(session_instance_id=instance.id).all()
    }

    if request.method == "POST":
        was_flagged = instance.status == SessionInstance.STATUS_FLAGGED
        for student in roster:
            status = request.form.get(f"status_{student.id}", "present")
            existing = existing_records.get(student.id)
            if existing:
                if existing.status != status:
                    log_attendance_change(existing, existing.status, status, current_user.id, reason="Roll call re-submitted")
                existing.status = status
                existing.marked_at = datetime.utcnow()
            else:
                db.session.add(
                    AttendanceRecord(
                        session_instance_id=instance.id, student_id=student.id,
                        status=status, marked_by=current_user.id,
                    )
                )
        instance.status = SessionInstance.STATUS_SUBMITTED
        instance.submitted_by = current_user.id
        instance.submitted_at = datetime.utcnow()
        instance.was_late = was_flagged or datetime.utcnow() > instance.grace_deadline
        draft = RollCallDraft.query.filter_by(session_instance_id=instance.id).first()
        if draft:
            db.session.delete(draft)
        db.session.commit()
        flash("Attendance submitted.", "success")
        return redirect(url_for("teacher.rollcall_success", session_instance_id=instance.id))

    return render_template(
        "teacher/rollcall.html", instance=instance, ts=ts, roster=roster, existing_records=existing_records
    )


VALID_STATUSES = {"present", "absent", "late"}


@teacher_bp.route("/sessions/<int:session_instance_id>/rollcall/draft", methods=["GET", "POST"])
def rollcall_draft(session_instance_id):
    """Server-side persistence for an in-progress roll call.

    The rollcall page auto-saves selections here so they survive a refresh,
    a browser crash, or the teacher switching devices — the localStorage copy
    is only the first-level cache.
    """
    instance = SessionInstance.query.get_or_404(session_instance_id)
    ts = instance.timetable_session
    if ts.teacher_id != current_user.id:
        abort(403)
    if instance.status == SessionInstance.STATUS_SUBMITTED:
        return jsonify({"error": "Roll call already submitted."}), 409

    draft = RollCallDraft.query.filter_by(session_instance_id=instance.id).first()

    if request.method == "POST":
        try:
            payload = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Invalid JSON body."}), 400
        if not isinstance(payload, dict):
            return jsonify({"error": "Expected a JSON object of student_id -> status."}), 400

        roster_ids = {
            e.student_id
            for e in StudentSubjectEnrollment.query.filter_by(
                subject_id=ts.subject_id, term_id=ts.term_id
            ).all()
        }
        clean = {}
        for key, value in payload.items():
            try:
                sid = int(key)
            except (TypeError, ValueError):
                continue
            if sid in roster_ids and value in VALID_STATUSES:
                clean[str(sid)] = value

        if draft is None:
            draft = RollCallDraft(
                session_instance_id=instance.id, teacher_id=current_user.id, payload="{}"
            )
            db.session.add(draft)
        draft.payload = json.dumps(clean)
        draft.teacher_id = current_user.id
        db.session.commit()
        return jsonify({"ok": True, "saved": len(clean)})

    # GET — return any saved draft for restore-on-load
    return jsonify({"payload": json.loads(draft.payload) if draft else {}})


@teacher_bp.route("/sessions/<int:session_instance_id>/rollcall/success")
def rollcall_success(session_instance_id):
    instance = SessionInstance.query.get_or_404(session_instance_id)
    if instance.timetable_session.teacher_id != current_user.id:
        abort(403)
    count = AttendanceRecord.query.filter_by(session_instance_id=instance.id).count()
    return render_template("teacher/rollcall_success.html", instance=instance, count=count)


@teacher_bp.route("/sessions/<int:session_instance_id>/rollcall/edit", methods=["GET", "POST"])
def rollcall_edit(session_instance_id):
    instance = SessionInstance.query.get_or_404(session_instance_id)
    ts = instance.timetable_session
    if ts.teacher_id != current_user.id:
        abort(403)
    if instance.status != SessionInstance.STATUS_SUBMITTED:
        return redirect(url_for("teacher.rollcall", session_instance_id=instance.id))

    records = AttendanceRecord.query.filter_by(session_instance_id=instance.id).join(Student).order_by(Student.full_name).all()

    if request.method == "POST":
        for r in records:
            new_status = request.form.get(f"status_{r.student_id}", r.status)
            if new_status != r.status:
                log_attendance_change(r, r.status, new_status, current_user.id, reason=request.form.get("reason", ""))
                r.status = new_status
        db.session.commit()
        flash("Roll call updated. Changes were logged to the audit trail.", "success")
        return redirect(url_for("teacher.dashboard"))

    return render_template("teacher/rollcall_edit.html", instance=instance, ts=ts, records=records)
