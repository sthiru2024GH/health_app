from flask import Blueprint, request, jsonify, session
from app.models import User
from app import db
from app.utils.captcha import create_login_captcha, verify_login_captcha
from app.utils.decorators import login_required

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/captcha', methods=['GET'])
def get_login_captcha():
    return jsonify({"captcha_question": create_login_captcha()}), 200


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password') or not data.get('name'):
        return jsonify({"error": "Missing required fields"}), 400

    role = data.get('role', 'patient')
    if not isinstance(role, str) or role not in {'patient', 'doctor'}:
        return jsonify({"error": "Select a valid account type"}), 400
        
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"error": "Username already exists"}), 400
        
    user = User(
        username=data['username'],
        name=data['name'],
        role=role
    )
    user.set_password(data['password'])
    
    if data.get('doctor_id'):
        user.doctor_id = data['doctor_id']
        
    db.session.add(user)
    db.session.commit()
    
    return jsonify({"message": "User registered successfully", "user_id": user.id}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"error": "Missing username or password"}), 400

    if not verify_login_captcha(data.get('captcha_answer')):
        return jsonify({
            "error": "Please solve the CAPTCHA to continue.",
            "captcha_question": create_login_captcha(),
        }), 400

    user = User.query.filter_by(username=data['username']).first()

    if user and user.check_password(data['password']):
        session.clear()
        session['user_id'] = user.id
        session['role'] = user.role
        session['name'] = user.name
        return jsonify({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "role": user.role
            }
        }), 200

    return jsonify({
        "error": "Invalid username or password",
        "captcha_question": create_login_captcha(),
    }), 401

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    session.pop('name', None)
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.route('/patients', methods=['GET'])
@login_required
def list_patients():
    if session.get('role') != 'guest':
        return jsonify({"error": "Guest access required"}), 403

    patients = User.query.filter_by(role='patient').order_by(User.name.asc(), User.id.asc()).all()
    return jsonify({
        "patients": [{"id": patient.id, "name": patient.name} for patient in patients]
    }), 200


@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
        
    return jsonify({
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "doctor_id": user.doctor_id
    }), 200
