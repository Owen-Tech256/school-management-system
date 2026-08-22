from app import create_app
from app.extensions import db
from app.models import Subject

app = create_app()
with app.app_context():
    subject = Subject.query.filter_by(name="MATHS").first()
    if not subject:
        print("MATHS not found")
    else:
        subject.is_elective = False
        db.session.commit()
        print("MATHS is now marked as compulsory (not elective).")