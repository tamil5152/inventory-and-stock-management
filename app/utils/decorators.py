from functools import wraps

from flask import abort
from flask_login import current_user


def role_required(*roles):
    """Allow the view only for logged-in users having one of the roles."""

    def decorator(view):

        @wraps(view)
        def wrapper(*args, **kwargs):

            if not current_user.is_authenticated:
                abort(401)

            if not current_user.has_role(*roles):
                abort(403)

            return view(*args, **kwargs)

        return wrapper

    return decorator
