import os
import csv
import io
import secrets
from datetime import datetime, timedelta, time as dtime

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app, send_file, abort
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    User, SchoolClass, Subject, Student, AcademicYear, Term,
    TimetableSession, SessionInstance, AttendanceRecord, AttendanceAuditLog,
    StudentSubjectEnrollment, TeacherSubjectAssignment
)
from app.forms import (
    UserForm, ClassForm, SubjectForm, StudentForm, AcademicYearForm, TermForm,
    TimetableCellForm
)
from app.utils import roles_required, current_term
from app.jobs.generate_sessions import run as generate_sessions_run
from app.services.enrollment_service import auto_enroll_student
from app.services.audit_service import log_attendance_change

admin_bp = Blueprint("admin", __name__)


@admin_bp.before_request
@login_required
def restrict_to_admins():
    if current_user.role not in (User.ROLE_SUPER_ADMIN, User.ROLE_ADMIN_STAFF):
        abort(403)


def _staff_only(fn):
    """Marker used on routes only Super Admin (not front office) may access."""
    return roles_required(User.ROLE_SUPER_ADMIN)(fn)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/dashboard")
def dashboard():
    term = current_term()

    total_students = Student.query.filter_by(is_active=True).count()
    flagged_today = SessionInstance.query.filter_by(
        status=SessionInstance.STATUS_FLAGGED, session_date=datetime.utcnow().date()
    ).count()

    overall_pct = None
    at_risk_students = []
    if term:
        records = (
            AttendanceRecord.query.join(SessionInstance).join(TimetableSession)
            .filter(TimetableSession.term_id == term.id).all()
        )
        if records:
            present_like = sum(1 for r in records if r.status in ("present", "late"))
            overall_pct = round((present_like / len(records)) * 100, 1)

        students = Student.query.filter_by(is_active=True).all()
        risk_threshold = 75.0
        for s in students:
            pct = s.attendance_percentage(term_id=term.id)
            if pct is not None and pct < risk_threshold:
                at_risk_students.append((s, pct))
        at_risk_students.sort(key=lambda pair: pair[1])
        at_risk_students = at_risk_students[:8]

    teachers_flagged = (
        db.session.query(TimetableSession.teacher_id, db.func.count(SessionInstance.id))
        .join(SessionInstance, SessionInstance.timetable_session_id == TimetableSession.id)
        .filter(SessionInstance.status == SessionInstance.STATUS_FLAGGED)
        .group_by(TimetableSession.teacher_id)
        .order_by(db.func.count(SessionInstance.id).desc())
        .limit(5)
        .all()
    )
    teacher_flag_rows = []
    for teacher_id, count in teachers_flagged:
        teacher = User.query.get(teacher_id)
        if teacher:
            teacher_flag_rows.append((teacher, count))

    return render_template(
        "admin/dashboard.html",
        term=term,
        total_students=total_students,
        flagged_today=flagged_today,
        overall_pct=overall_pct,
        at_risk_students=at_risk_students,
        teacher_flag_rows=teacher_flag_rows,
    )


# ---------------------------------------------------------------------------
# Academic Years / Terms
# ---------------------------------------------------------------------------

def _year_label_taken(label, exclude_id=None):
    """True if another academic year in this school already uses the label."""
    query = AcademicYear.query.filter(
        AcademicYear.school_id == current_user.school_id,
        db.func.lower(AcademicYear.label) == label.strip().lower(),
    )
    if exclude_id is not None:
        query = query.filter(AcademicYear.id != exclude_id)
    return query.first() is not None


@admin_bp.route("/academic-years", methods=["GET", "POST"])
@_staff_only
def academic_years():
    form = AcademicYearForm()
    if form.validate_on_submit():
        if _year_label_taken(form.label.data):
            form.label.errors.append("An academic year with this label already exists.")
        else:
            year = AcademicYear(
                school_id=current_user.school_id,
                label=form.label.data.strip(),
                start_date=form.start_date.data,
                end_date=form.end_date.data,
            )
            db.session.add(year)
            db.session.commit()
            flash("Academic year created.", "success")
            return redirect(url_for("admin.academic_years"))

    years = AcademicYear.query.filter_by(school_id=current_user.school_id).order_by(AcademicYear.label.desc()).all()
    return render_template("admin/academic_years.html", form=form, years=years)


@admin_bp.route("/academic-years/<int:year_id>/edit", methods=["GET", "POST"])
@_staff_only
def academic_year_edit(year_id):
    year = AcademicYear.query.filter_by(school_id=current_user.school_id).filter_by(id=year_id).first_or_404()
    form = AcademicYearForm(obj=year)
    if form.validate_on_submit():
        if _year_label_taken(form.label.data, exclude_id=year.id):
            form.label.errors.append("An academic year with this label already exists.")
        else:
            year.label = form.label.data.strip()
            year.start_date = form.start_date.data
            year.end_date = form.end_date.data
            db.session.commit()
            flash("Academic year updated.", "success")
            return redirect(url_for("admin.academic_years"))

    return render_template("admin/academic_year_edit.html", form=form, year=year)


@admin_bp.route("/terms", methods=["GET", "POST"])
@_staff_only
def terms():
    form = TermForm()
    form.academic_year_id.choices = [
        (y.id, y.label) for y in AcademicYear.query.filter_by(school_id=current_user.school_id).all()
    ]
    if form.validate_on_submit():
        if form.is_current.data:
            Term.query.update({Term.is_current: False})
        term = Term(
            academic_year_id=form.academic_year_id.data,
            name=form.name.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            is_current=form.is_current.data,
        )
        db.session.add(term)
        db.session.commit()
        flash("Term created.", "success")
        return redirect(url_for("admin.terms"))

    all_terms = Term.query.join(AcademicYear).filter(
        AcademicYear.school_id == current_user.school_id
    ).order_by(Term.start_date.desc()).all()
    return render_template("admin/terms.html", form=form, terms=all_terms)


@admin_bp.route("/terms/<int:term_id>/set-current", methods=["POST"])
@_staff_only
def set_current_term(term_id):
    Term.query.update({Term.is_current: False})
    term = Term.query.get_or_404(term_id)
    term.is_current = True
    db.session.commit()
    flash(f"{term.name} is now the current term.", "success")
    return redirect(url_for("admin.terms"))

@admin_bp.route("/terms/<int:term_id>/edit", methods=["GET", "POST"])
@_staff_only
def edit_term(term_id):
    term = Term.query.get_or_404(term_id)
    form = TermForm(obj=term)
    form.academic_year_id.choices = [
        (y.id, y.label) for y in AcademicYear.query.filter_by(school_id=current_user.school_id).all()
    ]
    if request.method == "GET":
        form.is_current.data = term.is_current

    if form.validate_on_submit():
        if form.is_current.data and not term.is_current:
            Term.query.update({Term.is_current: False})
        term.academic_year_id = form.academic_year_id.data
        term.name = form.name.data
        term.start_date = form.start_date.data
        term.end_date = form.end_date.data
        term.is_current = form.is_current.data
        db.session.commit()
        flash("Term updated.", "success")
        return redirect(url_for("admin.terms"))
    return render_template("admin/term_form.html", form=form, title="Edit term")


@admin_bp.route("/terms/<int:term_id>/delete", methods=["POST"])
@_staff_only
def delete_term(term_id):
    term = Term.query.get_or_404(term_id)
    timetable_count = TimetableSession.query.filter_by(term_id=term.id).count()
    enrollment_count = StudentSubjectEnrollment.query.filter_by(term_id=term.id).count()

    if timetable_count > 0 or enrollment_count > 0:
        flash(
            f"Can't delete {term.name} — it has {timetable_count} timetable slot(s) and "
            f"{enrollment_count} enrollment record(s) attached. Remove those first.",
            "error",
        )
        return redirect(url_for("admin.terms"))

    db.session.delete(term)
    db.session.commit()
    flash(f"{term.name} deleted.", "success")
    return redirect(url_for("admin.terms"))
# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@admin_bp.route("/users")
@_staff_only
def users():
    all_users = User.query.filter_by(school_id=current_user.school_id).order_by(User.full_name).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@_staff_only
def new_user():
    form = UserForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if existing:
            flash("A user with that email already exists.", "error")
        else:
            temp_password = secrets.token_urlsafe(9)
            user = User(
                school_id=current_user.school_id,
                role=form.role.data,
                full_name=form.full_name.data,
                email=form.email.data.lower().strip(),
                phone=form.phone.data,
                is_class_teacher=form.is_class_teacher.data,
                must_reset_password=True,
                created_by=current_user.id,
            )
            user.set_password(temp_password)
            db.session.add(user)
            db.session.commit()
            flash(
                f"Account created for {user.full_name}. Temporary password: {temp_password} "
                "(share this with them directly — it will not be shown again).",
                "success",
            )
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, title="New account")


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@_staff_only
def toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    user.is_active_account = not user.is_active_account
    db.session.commit()
    flash(f"{user.full_name} is now {'active' if user.is_active_account else 'inactive'}.", "success")
    return redirect(url_for("admin.users"))

@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@_staff_only
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    temp_password = secrets.token_urlsafe(9)
    user.set_password(temp_password)
    user.must_reset_password = True
    db.session.commit()
    flash(
        f"Temporary password for {user.full_name}: {temp_password} "
        "(share this with them directly — it will not be shown again).",
        "success",
    )
    return redirect(url_for("admin.users"))


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

@admin_bp.route("/classes")
@_staff_only
def classes():
    all_classes = SchoolClass.query.filter_by(school_id=current_user.school_id).all()
    return render_template("admin/classes.html", classes=all_classes)


@admin_bp.route("/classes/new", methods=["GET", "POST"])
@_staff_only
def new_class():
    form = ClassForm()
    form.academic_year_id.choices = [
        (y.id, y.label) for y in AcademicYear.query.filter_by(school_id=current_user.school_id).all()
    ]
    form.class_teacher_id.choices = [(0, "— None —")] + [
        (t.id, t.full_name) for t in User.query.filter_by(school_id=current_user.school_id, role=User.ROLE_TEACHER).all()
    ]
    if form.validate_on_submit():
        cls = SchoolClass(
            school_id=current_user.school_id,
            level=form.level.data.strip(),
            stream=form.stream.data.strip() or None,
            academic_year_id=form.academic_year_id.data,
            class_teacher_id=form.class_teacher_id.data or None,
        )
        db.session.add(cls)
        db.session.commit()
        flash("Class created.", "success")
        return redirect(url_for("admin.classes"))
    return render_template("admin/class_form.html", form=form, title="New class")

@admin_bp.route("/classes/<int:class_id>/edit", methods=["GET", "POST"])
@_staff_only
def edit_class(class_id):
    cls = SchoolClass.query.get_or_404(class_id)
    form = ClassForm(obj=cls)
    form.academic_year_id.choices = [
        (y.id, y.label) for y in AcademicYear.query.filter_by(school_id=current_user.school_id).all()
    ]
    form.class_teacher_id.choices = [(0, "— None —")] + [
        (t.id, t.full_name) for t in User.query.filter_by(school_id=current_user.school_id, role=User.ROLE_TEACHER).all()
    ]
    if request.method == "GET":
        form.class_teacher_id.data = cls.class_teacher_id or 0

    if form.validate_on_submit():
        cls.level = form.level.data.strip()
        cls.stream = form.stream.data.strip() or None
        cls.academic_year_id = form.academic_year_id.data
        cls.class_teacher_id = form.class_teacher_id.data or None
        db.session.commit()
        flash("Class updated.", "success")
        return redirect(url_for("admin.classes"))
    return render_template("admin/class_form.html", form=form, title="Edit class")


@admin_bp.route("/subjects/<int:subject_id>/edit", methods=["GET", "POST"])
@_staff_only
def edit_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    form = SubjectForm(obj=subject)
    if form.validate_on_submit():
        was_elective = subject.is_elective
        subject.name = form.name.data.strip()
        subject.is_elective = form.is_elective.data
        subject.expected_periods_per_week = form.expected_periods_per_week.data or 5
        db.session.commit()

        backfilled = 0
        if was_elective and not subject.is_elective:
            term = current_term()
            if term:
                students = Student.query.filter_by(school_id=current_user.school_id, is_active=True).all()
                for s in students:
                    backfilled += auto_enroll_student(s, term)

        msg = "Subject updated."
        if backfilled:
            msg += f" {backfilled} student(s) newly enrolled now that it's compulsory."
        flash(msg, "success")
        return redirect(url_for("admin.subjects"))
    return render_template("admin/subject_form.html", form=form, title="Edit subject")
# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

@admin_bp.route("/subjects")
@_staff_only
def subjects():
    all_subjects = Subject.query.filter_by(school_id=current_user.school_id).all()
    return render_template("admin/subjects.html", subjects=all_subjects)


@admin_bp.route("/subjects/new", methods=["GET", "POST"])
@_staff_only
def new_subject():
    form = SubjectForm()
    if form.validate_on_submit():
        subject = Subject(
            school_id=current_user.school_id,
            name=form.name.data.strip(),
            is_elective=form.is_elective.data,
            expected_periods_per_week=form.expected_periods_per_week.data or 5,
        )
        db.session.add(subject)
        db.session.commit()
        flash("Subject created.", "success")
        return redirect(url_for("admin.subjects"))
    return render_template("admin/subject_form.html", form=form, title="New subject")


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

@admin_bp.route("/students")
def students():
    q = request.args.get("q", "").strip()
    class_id = request.args.get("class_id", type=int)
    query = Student.query.filter_by(school_id=current_user.school_id, is_active=True)
    if q:
        query = query.filter(
            db.or_(Student.full_name.ilike(f"%{q}%"), Student.student_number.ilike(f"%{q}%"))
        )
    if class_id:
        query = query.filter_by(class_id=class_id)
    all_students = query.order_by(Student.full_name).all()
    all_classes = SchoolClass.query.filter_by(school_id=current_user.school_id).all()
    return render_template("admin/students.html", students=all_students, classes=all_classes, q=q, class_id=class_id)


@admin_bp.route("/students/new", methods=["GET", "POST"])
def new_student():
    form = StudentForm()
    form.class_id.choices = [
        (c.id, c.display_name) for c in SchoolClass.query.filter_by(school_id=current_user.school_id).all()
    ]
    if not form.class_id.choices:
        flash("Create a class before registering students.", "error")
        return redirect(url_for("admin.classes"))

    if form.validate_on_submit():
        existing = Student.query.filter_by(student_number=form.student_number.data.strip()).first()
        if existing:
            flash("A student with that student number already exists.", "error")
            return render_template("admin/student_form.html", form=form, title="Register student")

        student = Student(
            school_id=current_user.school_id,
            class_id=form.class_id.data,
            full_name=form.full_name.data.strip(),
            student_number=form.student_number.data.strip(),
            date_of_birth=form.date_of_birth.data,
            gender=form.gender.data or None,
            guardian_name=form.guardian_name.data,
            guardian_phone=form.guardian_phone.data,
            parental_consent_on_file=form.parental_consent_on_file.data,
            enrollment_date=datetime.utcnow().date(),
        )

        photo = form.photo.data
        if photo and photo.filename and student.parental_consent_on_file:
            filename = secure_filename(f"{form.student_number.data}_{photo.filename}")
            dest = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            photo.save(dest)
            student.photo_storage_path = f"uploads/student_photos/{filename}"

        db.session.add(student)
        db.session.commit()

        term = current_term()
        if term:
            auto_enroll_student(student, term)

        flash(f"{student.full_name} registered.", "success")
        return redirect(url_for("admin.student_profile", student_id=student.id))

    return render_template("admin/student_form.html", form=form, title="Register student")


@admin_bp.route("/students/<int:student_id>")
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
        read_only=False,
    )


# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------

PERIODS = list(range(1, 9))


@admin_bp.route("/timetable")
@_staff_only
def timetable():
    class_id = request.args.get("class_id", type=int)
    all_classes = SchoolClass.query.filter_by(school_id=current_user.school_id).all()
    term = current_term()
    grid = {}
    selected_class = None

    if class_id and term:
        selected_class = SchoolClass.query.get_or_404(class_id)
        sessions = TimetableSession.query.filter_by(class_id=class_id, term_id=term.id).all()
        for s in sessions:
            grid[(s.day_of_week, s.period_number)] = s

    return render_template(
        "admin/timetable.html",
        classes=all_classes,
        selected_class=selected_class,
        term=term,
        grid=grid,
        days=TimetableSession.DAYS,
        periods=PERIODS,
    )

@admin_bp.route("/timetable/cell", methods=["GET", "POST"])
@_staff_only
def timetable_cell():
    class_id = request.args.get("class_id", type=int) or request.form.get("class_id", type=int)
    day = request.args.get("day") or request.form.get("day_of_week")
    period = request.args.get("period", type=int) or request.form.get("period_number", type=int)
    term = current_term()
    if not (class_id and day and period and term):
        abort(400)

    school_class = SchoolClass.query.get_or_404(class_id)
    existing = TimetableSession.query.filter_by(
        class_id=class_id, term_id=term.id, day_of_week=day, period_number=period
    ).first()

    form = TimetableCellForm(obj=existing)
    form.subject_id.choices = [(s.id, s.name) for s in Subject.query.filter_by(school_id=current_user.school_id).all()]
    form.teacher_id.choices = [
        (t.id, t.full_name) for t in User.query.filter_by(school_id=current_user.school_id, role=User.ROLE_TEACHER).all()
    ]

    if not form.subject_id.choices or not form.teacher_id.choices:
        flash("Add at least one subject and one teacher before building the timetable.", "error")
        return redirect(url_for("admin.timetable", class_id=class_id))

    if form.validate_on_submit():
        clash = TimetableSession.query.filter(
            TimetableSession.term_id == term.id,
            TimetableSession.day_of_week == day,
            TimetableSession.period_number == period,
            TimetableSession.teacher_id == form.teacher_id.data,
            TimetableSession.class_id != class_id,
        ).first()
        if clash:
            flash(
                f"That teacher is already teaching {clash.school_class.display_name} at this day/period.",
                "error",
            )
            return render_template(
                "admin/timetable_cell.html", form=form, school_class=school_class, day=day, period=period
            )

        if existing:
            existing.subject_id = form.subject_id.data
            existing.teacher_id = form.teacher_id.data
            existing.start_time = form.start_time.data
            existing.end_time = form.end_time.data
            existing.room = form.room.data
        else:
            ts = TimetableSession(
                class_id=class_id,
                subject_id=form.subject_id.data,
                teacher_id=form.teacher_id.data,
                term_id=term.id,
                day_of_week=day,
                period_number=period,
                start_time=form.start_time.data,
                end_time=form.end_time.data,
                room=form.room.data,
            )
            db.session.add(ts)
        db.session.commit()
        generate_sessions_run()
        flash("Timetable slot saved. Today's session was generated automatically if it applies.", "success")
        return redirect(url_for("admin.timetable", class_id=class_id))

    return render_template(
        "admin/timetable_cell.html", form=form, school_class=school_class, day=day, period=period
    )

@admin_bp.route("/timetable/cell/<int:session_id>/delete", methods=["POST"])
@_staff_only
def delete_timetable_cell(session_id):
    ts = TimetableSession.query.get_or_404(session_id)
    class_id = ts.class_id
    db.session.delete(ts)
    db.session.commit()
    flash("Timetable slot removed.", "success")
    return redirect(url_for("admin.timetable", class_id=class_id))


@admin_bp.route("/timetable/import-template")
@_staff_only
def timetable_import_template():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["class", "stream", "day_of_week", "period_number", "start_time", "end_time", "subject", "teacher_email", "room"])
    writer.writerow(["S1", "Blue", "Mon", "1", "08:00", "09:00", "Mathematics", "teacher@example.com", "12"])
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="timetable_import_template.csv")


@admin_bp.route("/timetable/import", methods=["GET", "POST"])
@_staff_only
def timetable_import():
    term = current_term()
    if not term:
        flash("Set a current term before importing a timetable.", "error")
        return redirect(url_for("admin.terms"))

    preview_rows = []
    errors = []

    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Choose a CSV file to import.", "error")
            return redirect(url_for("admin.timetable_import"))

        reader = csv.DictReader(io.StringIO(file.stream.read().decode("utf-8")))
        to_create = []
        for i, row in enumerate(reader, start=2):
            row_errors = []
            level = (row.get("class") or "").strip()
            stream = (row.get("stream") or "").strip() or None
            school_class = SchoolClass.query.filter_by(
                school_id=current_user.school_id, level=level, stream=stream, academic_year_id=term.academic_year_id
            ).first()
            if not school_class:
                row_errors.append(f"class '{level} {stream or ''}' not found")

            subject = Subject.query.filter_by(school_id=current_user.school_id, name=(row.get("subject") or "").strip()).first()
            if not subject:
                row_errors.append(f"subject '{row.get('subject')}' not found")

            teacher = User.query.filter_by(email=(row.get("teacher_email") or "").strip().lower(), role=User.ROLE_TEACHER).first()
            if not teacher:
                row_errors.append(f"teacher '{row.get('teacher_email')}' not found")

            day = (row.get("day_of_week") or "").strip()
            if day not in TimetableSession.DAYS:
                row_errors.append(f"day_of_week '{day}' invalid (use Mon..Fri)")

            try:
                period = int(row.get("period_number"))
            except (TypeError, ValueError):
                period = None
                row_errors.append("period_number invalid")

            try:
                start_h, start_m = (row.get("start_time") or "").split(":")
                end_h, end_m = (row.get("end_time") or "").split(":")
                start_time = dtime(int(start_h), int(start_m))
                end_time = dtime(int(end_h), int(end_m))
            except Exception:
                start_time = end_time = None
                row_errors.append("start_time/end_time invalid (use HH:MM)")

            if not row_errors and school_class and teacher:
                clash = any(
                    r["teacher_id"] == teacher.id and r["day_of_week"] == day and r["period_number"] == period
                    for r in to_create
                )
                if clash:
                    row_errors.append("teacher already booked at this day/period in this import")

            if row_errors:
                errors.append(f"Row {i}: " + "; ".join(row_errors))
            else:
                to_create.append({
                    "class_id": school_class.id, "subject_id": subject.id, "teacher_id": teacher.id,
                    "term_id": term.id, "day_of_week": day, "period_number": period,
                    "start_time": start_time, "end_time": end_time, "room": (row.get("room") or "").strip(),
                    "label": f"{level} {stream or ''} · {subject.name} · {day} P{period}",
                })

        if errors:
            flash(f"{len(errors)} row(s) failed validation — nothing was imported. Fix and re-upload.", "error")
            return render_template("admin/timetable_import.html", errors=errors, preview_rows=[])

        for row in to_create:
            row.pop("label")
            db.session.add(TimetableSession(**row))
        db.session.commit()
        flash(f"Imported {len(to_create)} timetable slot(s).", "success")
        return redirect(url_for("admin.timetable"))

    return render_template("admin/timetable_import.html", errors=errors, preview_rows=preview_rows)


# ---------------------------------------------------------------------------
# Attendance Flags
# ---------------------------------------------------------------------------

@admin_bp.route("/attendance/flags")
def attendance_flags():
    missed = (
        SessionInstance.query.filter_by(status=SessionInstance.STATUS_FLAGGED)
        .join(TimetableSession)
        .order_by(SessionInstance.session_date.desc())
        .limit(100)
        .all()
    )

    term = current_term()
    at_risk = []
    if term:
        for s in Student.query.filter_by(school_id=current_user.school_id, is_active=True).all():
            pct = s.attendance_percentage(term_id=term.id)
            if pct is not None and pct < 75.0:
                at_risk.append((s, pct))
        at_risk.sort(key=lambda pair: pair[1])

    return render_template("admin/flags.html", missed=missed, at_risk=at_risk)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@admin_bp.route("/audit-log")
@_staff_only
def audit_log():
    entries = AttendanceAuditLog.query.order_by(AttendanceAuditLog.changed_at.desc()).limit(200).all()
    return render_template("admin/audit_log.html", entries=entries)


# ---------------------------------------------------------------------------
# Reports (stub endpoint — present from early on per design plan Section 8.9)
# ---------------------------------------------------------------------------

@admin_bp.route("/reports")
def reports():
    all_classes = SchoolClass.query.filter_by(school_id=current_user.school_id).all()

    class_id = request.args.get("class_id", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    preview_rows = []
    if start_date and end_date:
        query = (
            AttendanceRecord.query.join(SessionInstance).join(TimetableSession)
            .filter(SessionInstance.session_date >= start_date, SessionInstance.session_date <= end_date)
        )
        if class_id:
            query = query.filter(TimetableSession.class_id == class_id)
        preview_rows = query.order_by(SessionInstance.session_date.desc()).limit(200).all()

    return render_template(
        "admin/reports.html", classes=all_classes, preview_rows=preview_rows,
        class_id=class_id, start_date=start_date, end_date=end_date
    )


@admin_bp.route("/reports/export.csv")
def reports_export_csv():
    class_id = request.args.get("class_id", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if not (start_date and end_date):
        flash("Choose a date range before exporting.", "error")
        return redirect(url_for("admin.reports"))

    query = (
        AttendanceRecord.query.join(SessionInstance).join(TimetableSession)
        .filter(SessionInstance.session_date >= start_date, SessionInstance.session_date <= end_date)
    )
    if class_id:
        query = query.filter(TimetableSession.class_id == class_id)
    records = query.order_by(SessionInstance.session_date).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Class", "Subject", "Student", "Student Number", "Status", "Teacher"])
    for r in records:
        ts = r.session_instance.timetable_session
        writer.writerow([
            r.session_instance.session_date.isoformat(),
            ts.school_class.display_name,
            ts.subject.name,
            r.student.full_name,
            r.student.student_number,
            r.status,
            ts.teacher.full_name,
        ])

    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    filename = f"attendance_report_{start_date}_to_{end_date}.csv"
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=filename)