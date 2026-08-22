from functools import wraps
from flask import abort
from flask_login import current_user


def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def current_term():
    from app.models import Term
    return Term.query.filter_by(is_current=True).first()
