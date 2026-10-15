from flask import Blueprint, render_template, session, redirect, url_for
from app.utils.captcha import create_login_captcha

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

@main_bp.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('login.html', captcha_question=create_login_captcha())

@main_bp.route('/register')
def register():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('register.html')

@main_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
        
    role = session.get('role')
    if role == 'doctor':
        return render_template('doctor_dashboard.html')
    else:
        return render_template('patient_dashboard.html')
