from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request, session

from app import db
from app.models import Intervention, InterventionLog, Practitioner, SymptomEntry, User
from app.utils.decorators import login_required, require_role


interventions_bp = Blueprint('interventions', __name__)
METHODS = {'medication', 'surgery', 'procedure', 'others'}
MEDICATION_TYPES = {'one_time', 'periodic'}
FREQUENCY_UNITS = {'days', 'weeks', 'months'}


def _serialize_log(log):
    administered_at = log.administered_at
    if administered_at.tzinfo is None:
        administered_at = administered_at.replace(tzinfo=timezone.utc)
    return {
        'id': log.id,
        'administered_at': administered_at.isoformat(),
        'notes': log.notes,
    }


def _serialize_intervention(intervention):
    logs = intervention.logs.order_by(InterventionLog.administered_at.desc()).all()
    created_at = intervention.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        'id': intervention.id,
        'practitioner_id': intervention.practitioner_id,
        'practitioner_name': intervention.practitioner.name,
        'symptom_id': intervention.symptom_id,
        'symptom_description': intervention.symptom.description,
        'symptom_severity': intervention.symptom.severity,
        'method': intervention.method,
        'medication_type': intervention.medication_type,
        'drug_name': intervention.drug_name,
        'frequency_count': intervention.frequency_count,
        'frequency_unit': intervention.frequency_unit,
        'end_date': intervention.end_date.isoformat() if intervention.end_date else None,
        'diagnosis': intervention.diagnosis,
        'notes': intervention.notes,
        'status': intervention.status,
        'created_at': created_at.isoformat(),
        'logs': [_serialize_log(log) for log in logs],
    }


def _parse_datetime(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@interventions_bp.route('', methods=['GET'])
@login_required
def get_interventions():
    role = session.get('role')
    if role == 'patient':
        patient_id = session['user_id']
    elif role == 'guest':
        try:
            patient_id = int(request.args.get('patient_id', ''))
        except ValueError:
            return jsonify({'error': 'Select a patient to view interventions'}), 400
        patient = db.session.get(User, patient_id)
        if not patient or patient.role != 'patient':
            return jsonify({'error': 'Patient not found'}), 404
    else:
        return jsonify({'error': 'Patient access required'}), 403

    plans = Intervention.query.filter_by(
        patient_id=patient_id
    ).order_by(Intervention.created_at.desc()).all()
    return jsonify({'interventions': [_serialize_intervention(plan) for plan in plans]}), 200


@interventions_bp.route('', methods=['POST'])
@require_role('patient')
def create_intervention():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A valid intervention is required'}), 400

    method = data.get('method')
    notes = data.get('notes', '')
    if not isinstance(method, str) or method not in METHODS:
        return jsonify({'error': 'Select a valid intervention method'}), 400
    if not isinstance(notes, str):
        return jsonify({'error': 'Notes must be text'}), 400
    notes = notes.strip()
    if method == 'others' and not notes:
        return jsonify({'error': 'Notes are required for other interventions'}), 400

    try:
        practitioner_id = int(data.get('practitioner_id'))
        symptom_id = int(data.get('symptom_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Select a practitioner and symptom'}), 400

    patient_id = session['user_id']
    practitioner = db.session.get(Practitioner, practitioner_id)
    symptom = db.session.get(SymptomEntry, symptom_id)
    if not practitioner or practitioner.patient_id != patient_id:
        return jsonify({'error': 'Select one of your practitioners'}), 400
    if not symptom or symptom.patient_id != patient_id:
        return jsonify({'error': 'Select one of your recorded symptoms'}), 400

    plan = Intervention(
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        symptom_id=symptom_id,
        method=method,
        diagnosis=data.get('diagnosis') or None,
        notes=notes,
    )

    if method == 'medication':
        medication_type = data.get('medication_type')
        drug_name = data.get('drug_name')
        if not isinstance(medication_type, str) or medication_type not in MEDICATION_TYPES:
            return jsonify({'error': 'Select one-time or periodic medication'}), 400
        if not isinstance(drug_name, str) or not drug_name.strip():
            return jsonify({'error': 'Drug name is required for medication interventions'}), 400
        plan.medication_type = medication_type
        plan.drug_name = drug_name.strip()

        if medication_type == 'periodic':
            try:
                frequency_count = int(data.get('frequency_count'))
            except (TypeError, ValueError):
                return jsonify({'error': 'Enter a valid medication frequency'}), 400
            frequency_unit = data.get('frequency_unit')
            if (
                frequency_count < 1
                or not isinstance(frequency_unit, str)
                or frequency_unit not in FREQUENCY_UNITS
            ):
                return jsonify({'error': 'Frequency must be positive and use days, weeks, or months'}), 400
            plan.frequency_count = frequency_count
            plan.frequency_unit = frequency_unit
            end_date_value = data.get('end_date')
            if end_date_value:
                try:
                    plan.end_date = date.fromisoformat(end_date_value)
                except (TypeError, ValueError):
                    return jsonify({'error': 'Enter a valid intervention end date'}), 400

    db.session.add(plan)
    db.session.commit()
    return jsonify({'message': 'Intervention saved', 'id': plan.id}), 201


@interventions_bp.route('/<int:intervention_id>/logs', methods=['POST'])
@require_role('patient')
def create_intervention_log(intervention_id):
    plan = db.session.get(Intervention, intervention_id)
    if not plan or plan.patient_id != session['user_id']:
        return jsonify({'error': 'Intervention not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Administration details are required'}), 400

    administered_at_value = data.get('administered_at')
    notes = data.get('notes', '')
    if not administered_at_value or not isinstance(notes, str):
        return jsonify({'error': 'Date and time are required and notes must be text'}), 400

    try:
        administered_at = _parse_datetime(administered_at_value)
    except (TypeError, ValueError):
        return jsonify({'error': 'Enter a valid administration date and time'}), 400

    log = InterventionLog(
        intervention_id=plan.id,
        administered_at=administered_at,
        notes=notes.strip(),
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({'message': 'Intervention administration recorded', 'id': log.id}), 201


@interventions_bp.route('/logs/<int:log_id>', methods=['PUT'])
@require_role('patient')
def update_intervention_log(log_id):
    log = db.session.get(InterventionLog, log_id)
    if not log or log.intervention.patient_id != session['user_id']:
        return jsonify({'error': 'Intervention log not found'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Log details are required'}), 400

    administered_at_value = data.get('administered_at')
    notes = data.get('notes', '')
    if not administered_at_value or not isinstance(notes, str):
        return jsonify({'error': 'Date and time are required and notes must be text'}), 400

    try:
        log.administered_at = _parse_datetime(administered_at_value)
    except (TypeError, ValueError):
        return jsonify({'error': 'Enter a valid administration date and time'}), 400

    log.notes = notes.strip()
    db.session.commit()
    return jsonify({'message': 'Intervention log updated'}), 200


@interventions_bp.route('/<int:intervention_id>/close', methods=['POST'])
@require_role('patient')
def close_intervention(intervention_id):
    plan = db.session.get(Intervention, intervention_id)
    if not plan or plan.patient_id != session['user_id']:
        return jsonify({'error': 'Intervention not found'}), 404

    plan.status = 'closed'
    db.session.commit()
    return jsonify({'message': 'Intervention closed'}), 200

