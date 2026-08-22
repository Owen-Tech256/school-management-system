from app import create_app
from app.extensions import db
from app.models import Student, Term
from app.services.enrollment_service import auto_enroll_student

app = create_app()
with app.app_context():
    term = Term.query.filter_by(is_current=True).first()
    if not term:
        print("No current term set — set one first.")
    else:
        students = Student.query.filter_by(is_active=True).all()
        total_created = 0
        for s in students:
            created = auto_enroll_student(s, term)
            if created:
                print(f"{s.full_name}: enrolled into {created} subject(s)")
                total_created += created
        print(f"\nDone. {total_created} new enrollment record(s) created across {len(students)} student(s).")