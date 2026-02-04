from functools import wraps
from flask import session, abort


def require_web_permission(code: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            me = session.get("me") or {}
            perms = set(me.get("permissions") or [])
            if code not in perms:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
