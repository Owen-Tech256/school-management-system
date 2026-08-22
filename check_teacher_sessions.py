import sys
from datetime import datetime
from app import create_app
from app.models import User, Term, TimetableSession, SessionInstance

email = sys.argv[1].strip()

app = create_app()
with app.app_context():
    teacher = User.query.filter_by(email=email).first()
    if not teacher:
        print(f"No user found with email: {email}")
        sys.exit()

    print("Teacher:", teacher.full_name)

    term = Term.query.filter_by(is_current=True).first()
    print("Current term:", term.name if term else "NONE SET")

    today = datetime.utcnow().date()
    print("Today's date (server):", today, "-", today.strftime("%A"))

    slots = TimetableSession.query.filter_by(teacher_id=teacher.id).all()
    print(f"\nAll timetable slots for this teacher ({len(slots)} total):")
    for s in slots:
        print(f"  - {s.day_of_week} P{s.period_number} {s.start_time}-{s.end_time} | {s.school_class.display_name} {s.subject.name} | term: {s.term.name}")

    instances = SessionInstance.query.join(TimetableSession).filter(
        TimetableSession.teacher_id == teacher.id, SessionInstance.session_date == today
    ).all()
    print(f"\nSession instances generated for TODAY ({len(instances)} total):")
    for i in instances:
        print(f"  - {i.timetable_session.subject.name} | status: {i.status}")