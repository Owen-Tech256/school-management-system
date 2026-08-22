# School Attendance & Accountability Management System

A Flask + SQLAlchemy (SQLite by default) implementation of the design plan:
mandatory, timetable-linked digital roll call, automatic missed-rollcall
flagging, and real attendance visibility for the Director of Studies,
teachers, and front office.

**This build ships completely empty.** No demo school, students, teachers,
classes, subjects, or attendance data are inserted anywhere. The only thing
`flask seed-admin` creates is your school record and the first Director of
Studies (Super Admin) login — everything else you enter yourself.

## Stack

- Flask (Jinja2 server-rendered pages, no separate frontend build)
- SQLAlchemy ORM, SQLite by default (swap `DATABASE_URL` for Postgres/Supabase later — no code changes needed)
- Flask-Login (session auth) + Flask-WTF (forms, CSRF)
- Chart.js (loaded from CDN) for dashboard visualizations
- Premium navy / royal-blue / gold-on-ivory design system, per the design brief, with an optional dark mode

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then edit SECRET_KEY, SCHOOL_NAME, etc.

flask --app run.py init-db       # creates empty tables — no demo data
flask --app run.py seed-admin    # interactive prompt: creates your school + first DOS login

flask --app run.py run
```

Then open `http://localhost:5000` and log in with the Super Admin account
you just created.

## First-time setup order (in the app)

Empty tables mean nothing works until this sequence is followed once:

1. **Terms & Years** — create an Academic Year, then a Term, and mark it current.
2. **Subjects** — add your subjects (mark electives if any).
3. **Users** — create teacher and front-office accounts (temporary passwords are shown once — share them directly).
4. **Classes** — create classes/streams, optionally assigning a class teacher.
5. **Students** — register students (photo + signed consent checkbox); they auto-enroll into every non-elective subject for the current term.
6. **Timetable** — build the weekly grid per class (manual, cell by cell) or use **Bulk Import** with the downloadable CSV template.
7. Once the timetable exists, run the scheduled jobs (see below) to generate today's sessions so teachers see them on their dashboard.

## Scheduled jobs

Two background jobs are required for the accountability logic to work.
They're implemented as CLI commands so your host's native cron (Render/Railway
scheduled jobs) can call them — this is more resilient than an in-process
scheduler:

```bash
flask --app run.py generate-sessions        # run once daily, e.g. 05:00
flask --app run.py flag-missed-rollcalls    # run every ~15 minutes during school hours
```

For local development, you can just run these manually whenever you want to
simulate "today's sessions" appearing on a teacher's dashboard.

## Project layout

```
app/
  models.py            # full schema: schools, years/terms, users, classes,
                        # subjects, enrollment, timetable, session instances,
                        # attendance records + audit log, students
  forms.py              # Flask-WTF forms
  extensions.py         # db, login_manager, csrf
  config.py             # Dev/Production config (SQLite by default)
  blueprints/
    auth/                # login, forced first-login password reset, logout
    admin/                # dashboard, users, classes, subjects, students,
                          # timetable (grid + bulk CSV import), attendance
                          # flags, audit log, reports, terms/years
    teacher/              # today's sessions, roll call, roll call edit
    lookup/                # front-office / parent-assisted read-only lookup
    dashboard/              # JSON endpoints feeding the Chart.js dashboards
  jobs/
    generate_sessions.py        # timetable template -> today's session instances
    flag_missed_rollcalls.py    # auto-flags sessions past their grace deadline
  services/
    enrollment_service.py    # auto-enrolls S1/S2 students into every subject
    audit_service.py          # writes attendance_audit_log entries on edits
  templates/, static/       # Jinja2 templates + the design system CSS
run.py
requirements.txt
.env.example
```

## Notes on scope vs. the original design plan

- **Bulk timetable import** uses CSV (not Excel/openpyxl) to keep dependencies
  light — the column shape matches the plan's template exactly, so exporting
  an existing Excel sheet to CSV first works fine.
- **Reports (PDF/CSV export)** is scaffolded as a real page and route, per the
  plan's note that it "should exist as a stub from early on" — the
  configuration UI is there; wire up the actual PDF/CSV generation when you're
  ready (e.g. with `reportlab` or `pandas`).
- **Parent self-service login** and **student self-login** are Phase 2 per the
  design plan and are not built here; the `parent_access` table is reserved
  in the schema (`ParentAccess` model) so no migration is needed later.
- **Alembic migrations** aren't wired up — `flask init-db` uses
  `db.create_all()`, which is appropriate for a fresh SQLite deployment. Add
  Alembic when you're ready to manage schema changes against a live Postgres
  database.
- **APScheduler / native cron** — the two scheduled jobs are plain CLI
  commands (see above) so you can wire them to whichever scheduler your host
  supports without any code changes.

## Security notes

- Passwords are hashed with Werkzeug (scrypt-based), never stored plain.
- Every form is CSRF-protected via Flask-WTF.
- Teachers can only view/submit roll call for sessions where they are the
  assigned teacher (enforced server-side, not just hidden in the UI).
- Editing an already-submitted roll call always writes to the audit log —
  there is no code path that silently overwrites a status.
- Student photos are stored under `app/static/uploads/student_photos/` and
  are only saved when the parental consent checkbox is confirmed at
  registration. For a real deployment behind Postgres/Supabase, move this to
  a private bucket with signed URLs, as the original design plan specifies —
  the local filesystem here is a stand-in appropriate for SQLite/dev use.
