from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


# ---------------------------------------------------------------------------
# School / Academic structure
# ---------------------------------------------------------------------------

class School(db.Model):
    __tablename__ = "schools"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    academic_years = db.relationship("AcademicYear", backref="school", lazy=True)
    classes = db.relationship("SchoolClass", backref="school", lazy=True)
    subjects = db.relationship("Subject", backref="school", lazy=True)
    users = db.relationship("User", backref="school", lazy=True)
    students = db.relationship("Student", backref="school", lazy=True)


class AcademicYear(db.Model):
    __tablename__ = "academic_years"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    label = db.Column(db.String(20), nullable=False)  # e.g. "2026"
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)

    terms = db.relationship("Term", backref="academic_year", lazy=True, cascade="all, delete-orphan")


class Term(db.Model):
    __tablename__ = "terms"

    id = db.Column(db.Integer, primary_key=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_years.id"), nullable=False)
    name = db.Column(db.String(50), nullable=False)  # e.g. "Term 1"
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_current = db.Column(db.Boolean, default=False)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"

    ROLE_SUPER_ADMIN = "super_admin"
    ROLE_ADMIN_STAFF = "admin_staff"
    ROLE_TEACHER = "teacher"
    ROLES = [ROLE_SUPER_ADMIN, ROLE_ADMIN_STAFF, ROLE_TEACHER]

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)
    must_reset_password = db.Column(db.Boolean, default=True)
    is_active_account = db.Column(db.Boolean, default=True)
    is_class_teacher = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    # Flask-Login required properties
    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.is_active_account

    @property
    def role_label(self):
        return {
            self.ROLE_SUPER_ADMIN: "Director of Studies",
            self.ROLE_ADMIN_STAFF: "Front Office",
            self.ROLE_TEACHER: "Teacher",
        }.get(self.role, self.role)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


# ---------------------------------------------------------------------------
# Classes / Subjects / Enrollment
# ---------------------------------------------------------------------------

class SchoolClass(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    level = db.Column(db.String(10), nullable=False)   # S1..S6
    stream = db.Column(db.String(50), nullable=True)   # Blue, Red...
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_years.id"), nullable=False)
    class_teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    class_teacher = db.relationship("User", foreign_keys=[class_teacher_id])
    students = db.relationship("Student", backref="school_class", lazy=True)

    @property
    def display_name(self):
        return f"{self.level} {self.stream}" if self.stream else self.level


class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_elective = db.Column(db.Boolean, default=False)
    expected_periods_per_week = db.Column(db.Integer, default=5)


class StudentSubjectEnrollment(db.Model):
    __tablename__ = "student_subject_enrollment"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey("terms.id"), nullable=False)

    student = db.relationship("Student", backref="enrollments")
    subject = db.relationship("Subject")
    term = db.relationship("Term")

    __table_args__ = (
        db.UniqueConstraint("student_id", "subject_id", "term_id", name="uq_student_subject_term"),
    )


class TeacherSubjectAssignment(db.Model):
    __tablename__ = "teacher_subject_assignment"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey("terms.id"), nullable=False)

    teacher = db.relationship("User")
    subject = db.relationship("Subject")
    school_class = db.relationship("SchoolClass")
    term = db.relationship("Term")


# ---------------------------------------------------------------------------
# Timetable & Sessions
# ---------------------------------------------------------------------------

class TimetableSession(db.Model):
    """The recurring weekly template slot."""
    __tablename__ = "timetable_sessions"

    DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey("terms.id"), nullable=False)
    day_of_week = db.Column(db.String(3), nullable=False)  # Mon..Fri
    period_number = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room = db.Column(db.String(50))

    school_class = db.relationship("SchoolClass")
    subject = db.relationship("Subject")
    teacher = db.relationship("User")
    term = db.relationship("Term")


class SessionInstance(db.Model):
    """One concrete, dated occurrence of a TimetableSession."""
    __tablename__ = "session_instances"

    STATUS_SCHEDULED = "scheduled"
    STATUS_SUBMITTED = "rollcall_submitted"
    STATUS_FLAGGED = "flagged_missed"
    STATUS_CANCELLED = "cancelled"

    id = db.Column(db.Integer, primary_key=True)
    timetable_session_id = db.Column(db.Integer, db.ForeignKey("timetable_sessions.id"), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default=STATUS_SCHEDULED)
    submitted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    grace_deadline = db.Column(db.DateTime, nullable=False)
    was_late = db.Column(db.Boolean, default=False)

    timetable_session = db.relationship("TimetableSession")
    submitter = db.relationship("User")
    attendance_records = db.relationship("AttendanceRecord", backref="session_instance", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("timetable_session_id", "session_date", name="uq_session_instance_date"),
    )


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"

    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_LATE = "late"
    STATUS_EXCUSED = "excused"

    id = db.Column(db.Integer, primary_key=True)
    session_instance_id = db.Column(db.Integer, db.ForeignKey("session_instances.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    status = db.Column(db.String(10), nullable=False, default=STATUS_PRESENT)
    marked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student")
    marker = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("session_instance_id", "student_id", name="uq_attendance_session_student"),
    )


class AttendanceAuditLog(db.Model):
    __tablename__ = "attendance_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    attendance_record_id = db.Column(db.Integer, db.ForeignKey("attendance_records.id"), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    old_status = db.Column(db.String(10))
    new_status = db.Column(db.String(10))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.String(300))

    attendance_record = db.relationship("AttendanceRecord")
    changer = db.relationship("User")


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    student_number = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(10))
    guardian_name = db.Column(db.String(150))
    guardian_phone = db.Column(db.String(30))
    photo_storage_path = db.Column(db.String(300), nullable=True)
    enrollment_date = db.Column(db.Date, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    parental_consent_on_file = db.Column(db.Boolean, default=False)

    def attendance_percentage(self, term_id=None):
        query = AttendanceRecord.query.filter_by(student_id=self.id)
        if term_id:
            query = query.join(SessionInstance).join(TimetableSession).filter(
                TimetableSession.term_id == term_id
            )
        records = query.all()
        if not records:
            return None
        present_like = sum(1 for r in records if r.status in ("present", "late"))
        return round((present_like / len(records)) * 100, 1)


class ParentAccess(db.Model):
    """Reserved for Phase 2 parent self-service login. Not used in v1."""
    __tablename__ = "parent_access"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    access_code_hash = db.Column(db.String(255))
    phone = db.Column(db.String(30))
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_at = db.Column(db.DateTime, nullable=True)
