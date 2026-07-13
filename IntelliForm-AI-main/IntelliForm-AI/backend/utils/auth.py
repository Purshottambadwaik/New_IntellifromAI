"""
JWT authentication utilities.
- Token generation & verification
- login_required decorator (checks HTTP-only cookie)
"""

import jwt
import datetime
from functools import wraps
from flask import request, redirect, flash, g, make_response
import config


# ── Token Management ──────────────────────────────────────────────────────────

def generate_token(email):
    """Create a JWT token with email and expiry."""
    payload = {
        "email": email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=config.JWT_TOKEN_EXPIRY_HOURS),
        "iat": datetime.datetime.utcnow()
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm="HS256")


def decode_token(token):
    """Decode and verify a JWT token. Returns email or None."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload.get("email")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── Cookie Helpers ────────────────────────────────────────────────────────────

def set_auth_cookie(response, token):
    """Set JWT token as an HTTP-only cookie on the response."""
    response.set_cookie(
        'auth_token',
        token,
        httponly=True,       # JS can't read it (XSS protection)
        samesite='Lax',      # CSRF protection
        max_age=config.JWT_TOKEN_EXPIRY_HOURS * 3600,
        path='/'
    )
    return response


def clear_auth_cookie(response):
    """Remove the auth cookie."""
    response.delete_cookie('auth_token', path='/')
    return response


# ── Decorator ─────────────────────────────────────────────────────────────────

def login_required(f):
    """
    Decorator that checks for a valid JWT in the auth_token cookie.
    If valid, sets g.current_user_email so routes can access the logged-in user.
    If invalid/missing, redirects to /login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get('auth_token')

        if not token:
            flash("Please log in to continue.")
            return redirect('/login')

        email = decode_token(token)
        if not email:
            flash("Session expired. Please log in again.")
            return redirect('/login')

        # Make the current user's email available to the route
        g.current_user_email = email
        return f(*args, **kwargs)

    return decorated_function
