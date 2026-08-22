from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models import User
from app.forms import LoginForm, SetPasswordForm

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.is_active_account and user.check_password(form.password.data):
            login_user(user)
            if user.must_reset_password:
                return redirect(url_for("auth.force_reset_password"))
            return redirect(_role_landing(user))
        flash("Incorrect email or password.", "error")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
@login_required
def force_reset_password():
    if not current_user.must_reset_password:
        return redirect(_role_landing(current_user))

    form = SetPasswordForm()
    if form.validate_on_submit():
        current_user.set_password(form.password.data)
        current_user.must_reset_password = False
        db.session.commit()
        flash("Password updated. Welcome in.", "success")
        return redirect(_role_landing(current_user))
    return render_template("auth/reset_password.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


def _role_landing(user):
    if user.role == User.ROLE_TEACHER:
        return url_for("teacher.dashboard")
    return url_for("admin.dashboard")
