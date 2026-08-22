from app import create_app
from app.models import Student, Subject, Term, StudentSubjectEnrollment

app = create_app()
with app.app_context():
    term = Term.query.filter_by(is_current=True).first()
    print("Current term:", term.name if term else "NONE")

    print("\nAll subjects:")
    for s in Subject.query.all():
        print(f"  - {s.name} | elective: {s.is_elective} | school_id: {s.school_id}")

    print("\nStudents in S4:")
    students = [s for s in Student.query.all() if s.school_class.display_name.startswith("S4")]
    for s in students:
        print(f"  - {s.full_name} | school_id: {s.school_id}")
        enrollments = StudentSubjectEnrollment.query.filter_by(student_id=s.id).all()
        print(f"    enrolled in {len(enrollments)} subject(s)")