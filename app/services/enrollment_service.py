"""Section 6.2 / 10.6 — student_subject_enrollment auto-fill for S1/S2.

For S1/S2 (non-elective structure) a student is auto-enrolled into every
subject offered school-wide for the current term. This is what makes the
student appear automatically on every relevant teacher's roster.

For S3+ this same table is used, but enrollment would instead be built from
explicit elective selections made in the admin UI (not implemented in v1 —
the schema does not need to change when that is added).
"""
from app.extensions import db
from app.models import Subject, StudentSubjectEnrollment


def auto_enroll_student(student, term):
    """Enroll `student` into every non-elective subject for `term`."""
    subjects = Subject.query.filter_by(school_id=student.school_id, is_elective=False).all()
    created = 0
    for subject in subjects:
        exists = StudentSubjectEnrollment.query.filter_by(
            student_id=student.id, subject_id=subject.id, term_id=term.id
        ).first()
        if exists:
            continue
        db.session.add(
            StudentSubjectEnrollment(student_id=student.id, subject_id=subject.id, term_id=term.id)
        )
        created += 1
    db.session.commit()
    return created
