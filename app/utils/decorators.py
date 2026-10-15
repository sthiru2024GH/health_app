from functools import wraps
from flask import session, jsonify
from app.models import User

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

def require_role(role_or_roles):
    """
    Decorator to ensure the logged-in user has the required role(s).
    Can pass a single role (string) or multiple roles (list/tuple).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({"error": "Authentication required"}), 401
            
            user_role = session.get('role')
            if isinstance(role_or_roles, (list, tuple)):
                if user_role not in role_or_roles:
                    return jsonify({"error": f"Requires one of roles: {', '.join(role_or_roles)}"}), 403
            else:
                if user_role != role_or_roles:
                    return jsonify({"error": f"Requires role: {role_or_roles}"}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
