"""Section 6.2 / 10.5 — every edit to an already-submitted attendance record
writes to attendance_audit_log instead of silently overwriting."""
from datetime import datetime
from app.extensions import db
from app.models import AttendanceAuditLog


def log_attendance_change(record, old_status, new_status, changed_by_id, reason=None):
    entry = AttendanceAuditLog(
        attendance_record_id=record.id,
        changed_by=changed_by_id,
        old_status=old_status,
        new_status=new_status,
        changed_at=datetime.utcnow(),
        reason=reason,
    )
    db.session.add(entry)
