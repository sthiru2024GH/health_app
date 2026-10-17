from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session

from app import db
from app.models import SymptomEntry, User
from app.utils.decorators import login_required, require_role


symptoms_bp = Blueprint('symptoms', __name__)
SEVERITIES = {'mild', 'moderate', 'major', 'critical'}


@symptoms_bp.route('', methods=['GET'])
@login_required
def get_symptoms():
    role = session.get('role')
    if role == 'patient':
        patient_id = session['user_id']
    elif role == 'guest':
        try:
            patient_id = int(request.args.get('patient_id', ''))
        except ValueError:
            return jsonify({'error': 'Select a patient to view symptoms'}), 400
        patient = db.session.get(User, patient_id)
        if not patient or patient.role != 'patient':
            return jsonify({'error': 'Patient not found'}), 404
    else:
        return jsonify({'error': 'Patient access required'}), 403

    entries = SymptomEntry.query.filter_by(
        patient_id=patient_id
    ).order_by(SymptomEntry.recorded_at.desc()).all()

    return jsonify({
        'symptoms': [
            {
                'id': entry.id,
                'recorded_at': entry.recorded_at.isoformat(),
                'severity': entry.severity,
                'description': entry.description,
            }
            for entry in entries
        ]
    }), 200


@symptoms_bp.route('', methods=['POST'])
@require_role('patient')
def create_symptom():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A valid symptom entry is required'}), 400

    recorded_at_value = data.get('recorded_at')
    severity = data.get('severity')
    description = data.get('description')
    if not recorded_at_value or not severity or not isinstance(description, str) or not description.strip():
        return jsonify({'error': 'Date and time, severity, and symptom details are required'}), 400

    if not isinstance(severity, str) or severity not in SEVERITIES:
        return jsonify({'error': 'Severity must be mild, moderate, major, or critical'}), 400

    try:
        recorded_at = datetime.fromisoformat(recorded_at_value)
    except (TypeError, ValueError):
        return jsonify({'error': 'Enter a valid date and time'}), 400

    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    else:
        recorded_at = recorded_at.astimezone(timezone.utc)

    entry = SymptomEntry(
        patient_id=session['user_id'],
        recorded_at=recorded_at,
        severity=severity,
        description=description.strip(),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'message': 'Symptom recorded', 'id': entry.id}), 201
