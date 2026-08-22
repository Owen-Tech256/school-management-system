from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models import SchoolClass, Student, AttendanceRecord, SessionInstance
from app.utils import current_term

lookup_bp = Blueprint("lookup", __name__)


@lookup_bp.before_request
@login_required
def restrict_to_logged_in():
    pass


@lookup_bp.route("/classes")
def classes():
    q = request.args.get("q", "").strip()
    query = SchoolClass.query
    all_classes = query.all()
    if q:
        all_classes = [c for c in all_classes if q.lower() in c.display_name.lower()]
    return render_template("lookup/classes.html", classes=all_classes, q=q)


@lookup_bp.route("/classes/<int:class_id>/students")
def class_students(class_id):
    school_class = SchoolClass.query.get_or_404(class_id)
    students = Student.query.filter_by(class_id=class_id, is_active=True).order_by(Student.full_name).all()
    return render_template("lookup/students.html", school_class=school_class, students=students)


@lookup_bp.route("/students/<int:student_id>")
def student_profile(student_id):
    student = Student.query.get_or_404(student_id)
    term = current_term()
    overall_pct = student.attendance_percentage(term_id=term.id if term else None)

    records = (
        AttendanceRecord.query.filter_by(student_id=student.id)
        .join(SessionInstance).order_by(SessionInstance.session_date.desc()).limit(30).all()
    )
    subject_breakdown = {}
    for r in records:
        subject_name = r.session_instance.timetable_session.subject.name
        subject_breakdown.setdefault(subject_name, {"present": 0, "total": 0})
        subject_breakdown[subject_name]["total"] += 1
        if r.status in ("present", "late"):
            subject_breakdown[subject_name]["present"] += 1

    recent_absences = [r for r in records if r.status == "absent"][:10]

    return render_template(
        "admin/student_profile.html",
        student=student,
        overall_pct=overall_pct,
        subject_breakdown=subject_breakdown,
        recent_absences=recent_absences,
        records=records,
        read_only=True,
    )
