from flask import Blueprint, render_template, request, redirect, flash, make_response
from models.user_store import create_user, find_user_by_email, verify_password, update_user_password
from utils.auth import generate_token, set_auth_cookie, clear_auth_cookie, login_required

auth_bp = Blueprint('auth', __name__)


# ── HOME ─────────────────────────────────────────────────────────────────────

@auth_bp.route('/')
def home():
    return render_template('index.html')


# ── SIGNUP ───────────────────────────────────────────────────────────────────

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name     = request.form.get('name', '')
        email    = request.form.get('email', '')
        password = request.form.get('password', '')

        if not email or not password:
            flash("Email and password are required.", "error")
            return redirect('/signup')

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect('/signup')

        user = create_user(email, password, name)

        if user is None:
            flash("Email already registered.", "error")
            return redirect('/signup')

        # Auto-login after signup and redirect to profile to complete it
        token = generate_token(email)
        response = make_response(redirect('/profile'))
        set_auth_cookie(response, token)
        flash("Account created! Please complete your profile.", "success")
        return response

    return render_template('signup.html')


# ── LOGIN ────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '')
        password = request.form.get('password', '')

        user = find_user_by_email(email)

        if user and verify_password(password, user['password']):
            # Generate JWT and set as HTTP-only cookie
            token = generate_token(email)
            response = make_response(redirect('/dashboard'))
            set_auth_cookie(response, token)
            flash("Login successful!", "success")
            return response

        flash("Invalid email or password.", "error")

    return render_template('login.html')


# ── FORGOT PASSWORD ──────────────────────────────────────────────────────────

@auth_bp.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        email        = request.form.get('email', '')
        new_password = request.form.get('new_password', '')

        if not email or not new_password:
            flash("Please fill in both fields.", "error")
            return redirect('/forgot')

        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect('/forgot')

        user = find_user_by_email(email)

        if user:
            update_user_password(email, new_password)
            flash("Password updated successfully!", "success")
            return redirect('/login')

        flash("Email not found.", "error")

    return render_template('forgot.html')


# ── LOGOUT ───────────────────────────────────────────────────────────────────

@auth_bp.route('/logout')
def logout():
    response = make_response(redirect('/login'))
    clear_auth_cookie(response)
    flash("Logged out successfully.", "info")
    return response
