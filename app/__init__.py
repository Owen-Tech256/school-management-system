import os
import click
from flask import Flask, render_template
from app.config import config_by_name
from app.extensions import db, login_manager, csrf


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.blueprints.auth.routes import auth_bp
    from app.blueprints.admin.routes import admin_bp
    from app.blueprints.teacher.routes import teacher_bp
    from app.blueprints.lookup.routes import lookup_bp
    from app.blueprints.dashboard.routes import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(teacher_bp, url_prefix="/teacher")
    app.register_blueprint(lookup_bp, url_prefix="/lookup")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    from flask_login import current_user

    from flask_login import current_user

    @app.before_request
    def enforce_password_reset():
        from flask import request, redirect, url_for
        if current_user.is_authenticated and current_user.must_reset_password:
            allowed = {"auth.force_reset_password", "auth.logout", "static"}
            if request.endpoint not in allowed:
                return redirect(url_for("auth.force_reset_password"))

    @app.route("/")
    def index():
        from flask import redirect, url_for
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role == "teacher":
            return redirect(url_for("teacher.dashboard"))
        return redirect(url_for("admin.dashboard"))

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    register_cli(app)

    @app.context_processor
    def inject_globals():
        return {"school_name": app.config.get("SCHOOL_NAME", "School")}

    return app


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables (empty, no demo data)."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("seed-admin")
    @click.option("--school-name", prompt="School name")
    @click.option("--full-name", prompt="Your full name")
    @click.option("--email", prompt="Admin email")
    @click.option("--password", prompt="Admin password", hide_input=True, confirmation_prompt=True)
    def seed_admin(school_name, full_name, email, password):
        """Create the school record and the first Super Admin (DOS) account.
        This is the ONLY account created automatically — no demo students,
        teachers, classes, or attendance data are ever inserted.
        """
        from app.models import School, User

        db.create_all()

        school = School.query.first()
        if not school:
            school = School(name=school_name)
            db.session.add(school)
            db.session.flush()

        existing = User.query.filter_by(email=email).first()
        if existing:
            click.echo(f"A user with email {email} already exists.")
            return

        admin = User(
            school_id=school.id,
            role=User.ROLE_SUPER_ADMIN,
            full_name=full_name,
            email=email,
            must_reset_password=False,
            is_active_account=True,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Super Admin '{full_name}' created for {school.name}. You can now log in.")

    @app.cli.command("generate-sessions")
    def generate_sessions_cmd():
        """Generate today's session_instances from the active timetable template."""
        from app.jobs.generate_sessions import run
        count = run()
        click.echo(f"Generated {count} session instance(s) for today.")

    @app.cli.command("reset-password")
    @click.option("--email", prompt="User's email")
    @click.option("--password", prompt="New password", hide_input=True, confirmation_prompt=True)
    def reset_password_cmd(email, password):
        """Reset any user's password and clear their forced-reset flag."""
        from app.models import User
        user = User.query.filter_by(email=email).first()
        if not user:
            click.echo(f"No user found with email {email}")
            return
        user.set_password(password)
        user.must_reset_password = False
        db.session.commit()
        click.echo(f"Password reset for {user.full_name} ({user.email}).")

    @app.cli.command("flag-missed-rollcalls")
    def flag_missed_cmd():
        """Flag any scheduled sessions whose grace period has elapsed."""
        from app.jobs.flag_missed_rollcalls import run
        count = run()
        click.echo(f"Flagged {count} session(s) as missed.")
