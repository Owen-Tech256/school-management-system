import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    GRACE_PERIOD_MINUTES = int(os.environ.get("GRACE_PERIOD_MINUTES", 20))
    SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "Your School Name")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads", "student_photos")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB photo upload cap


class DevConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "attendance.db")
    )
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "attendance.db")
    )
    SESSION_COOKIE_SECURE = True


config_by_name = {
    "development": DevConfig,
    "production": ProductionConfig,
}
