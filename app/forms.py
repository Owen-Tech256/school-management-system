from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, SelectField, BooleanField, DateField,
    TimeField, IntegerField, TextAreaField, HiddenField
)
from wtforms.validators import DataRequired, Email, Optional, Length, EqualTo


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])


class SetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirm new password", validators=[DataRequired(), EqualTo("password", message="Passwords must match")]
    )


class UserForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    role = SelectField(
        "Role",
        choices=[("teacher", "Teacher"), ("admin_staff", "Front Office"), ("super_admin", "Director of Studies")],
        validators=[DataRequired()],
    )
    is_class_teacher = BooleanField("Class teacher (form teacher)")


class ClassForm(FlaskForm):
    level = StringField("Level (e.g. S1, S2)", validators=[DataRequired(), Length(max=10)])
    stream = StringField("Stream (e.g. Blue, Red)", validators=[Optional(), Length(max=50)])
    academic_year_id = SelectField("Academic year", coerce=int, validators=[DataRequired()])
    class_teacher_id = SelectField("Class teacher", coerce=int, validators=[Optional()])


class SubjectForm(FlaskForm):
    name = StringField("Subject name", validators=[DataRequired(), Length(max=100)])
    is_elective = BooleanField("Elective subject")
    expected_periods_per_week = IntegerField("Expected periods / week", default=5, validators=[Optional()])


class StudentForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=150)])
    student_number = StringField("Student number", validators=[DataRequired(), Length(max=30)])
    class_id = SelectField("Class", coerce=int, validators=[DataRequired()])
    date_of_birth = DateField("Date of birth", validators=[Optional()])
    gender = SelectField("Gender", choices=[("", "Select"), ("Male", "Male"), ("Female", "Female")], validators=[Optional()])
    guardian_name = StringField("Guardian name", validators=[Optional(), Length(max=150)])
    guardian_phone = StringField("Guardian phone", validators=[Optional(), Length(max=30)])
    photo = FileField("Student photo", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png"], "Images only")])
    parental_consent_on_file = BooleanField("Parent/guardian has signed photo consent", validators=[DataRequired()])


class AcademicYearForm(FlaskForm):
    label = StringField("Year label (e.g. 2026)", validators=[DataRequired(), Length(max=20)])
    start_date = DateField("Start date", validators=[Optional()])
    end_date = DateField("End date", validators=[Optional()])


class TermForm(FlaskForm):
    academic_year_id = SelectField("Academic year", coerce=int, validators=[DataRequired()])
    name = StringField("Term name (e.g. Term 1)", validators=[DataRequired(), Length(max=50)])
    start_date = DateField("Start date", validators=[Optional()])
    end_date = DateField("End date", validators=[Optional()])
    is_current = BooleanField("Set as current term")


class TimetableCellForm(FlaskForm):
    class_id = HiddenField()
    day_of_week = HiddenField()
    period_number = HiddenField()
    subject_id = SelectField("Subject", coerce=int, validators=[DataRequired()])
    teacher_id = SelectField("Teacher", coerce=int, validators=[DataRequired()])
    start_time = TimeField("Start time", validators=[DataRequired()])
    end_time = TimeField("End time", validators=[DataRequired()])
    room = StringField("Room", validators=[Optional(), Length(max=50)])


class RollCallEditForm(FlaskForm):
    status = SelectField(
        "Status",
        choices=[("present", "Present"), ("absent", "Absent"), ("late", "Late"), ("excused", "Excused")],
        validators=[DataRequired()],
    )
    reason = TextAreaField("Reason for change", validators=[Optional(), Length(max=300)])
