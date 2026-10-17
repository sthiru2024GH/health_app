# app/api/vitals.py
import math
from datetime import date, datetime, timezone
from flask import Blueprint, request, jsonify, session
from app import db
from app.models import User, VitalSign, MedicationLog, PrescriptionItem
from app.services.patient_service import get_patient_timeline_for_range
from app.utils.decorators import login_required

vitals_bp = Blueprint('vitals', __name__)

@vitals_bp.route('/record', methods=['POST'])
@login_required
def record_vitals():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    patient_id = data.get('patient_id')
    if isinstance(patient_id, bool) or not isinstance(patient_id, int):
        return jsonify({"error": "patient_id must be an integer"}), 400
    if session.get('role') == 'patient' and patient_id != session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403
    if not db.session.get(User, patient_id):
        return jsonify({"error": "Patient not found"}), 404

    numeric_fields = {
        'systolic': ('systolic_bp', True),
        'diastolic': ('diastolic_bp', True),
        'heart_rate': ('heart_rate', True),
        'blood_sugar': ('blood_sugar', False),
        'weight_kg': ('weight_kg', False),
    }
    vital_values = {}
    for field, (model_field, integer_only) in numeric_fields.items():
        value = data.get(field)
        if value is None or value == '':
            vital_values[model_field] = None
            continue
        if isinstance(value, bool):
            return jsonify({"error": f"{field} must be a positive number"}), 400
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return jsonify({"error": f"{field} must be a positive number"}), 400
        if not math.isfinite(numeric_value) or numeric_value <= 0:
            return jsonify({"error": f"{field} must be a positive number"}), 400
        if integer_only and not numeric_value.is_integer():
            return jsonify({"error": f"{field} must be a whole number"}), 400
        vital_values[model_field] = (
            int(numeric_value) if integer_only else numeric_value
        )

    if all(value is None for value in vital_values.values()):
        return jsonify({"error": "Enter at least one vital measurement"}), 400

    recorded_at = None
    if data.get('recorded_at'):
        try:
            recorded_at = datetime.fromisoformat(data['recorded_at'])
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
            recorded_at = recorded_at.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return jsonify({"error": "recorded_at must be a valid ISO datetime"}), 400

    med_log_id = None
    if data.get('medication_schedule_id') is not None:
        schedule_id = data['medication_schedule_id']
        if isinstance(schedule_id, bool) or not isinstance(schedule_id, int):
            return jsonify({"error": "medication_schedule_id must be an integer"}), 400
        item = db.session.get(PrescriptionItem, schedule_id)
        if not item:
            return jsonify({"error": "Prescription Item not found"}), 404
        if item.prescription.patient_id != patient_id:
            return jsonify({"error": "Unauthorized"}), 403
        med_log = MedicationLog(
            prescription_item_id=item.id,
            status=data.get('med_status', 'taken')
        )
        db.session.add(med_log)
        db.session.flush()
        med_log_id = med_log.id

    vital_entry = VitalSign(
        patient_id=patient_id,
        medication_log_id=med_log_id,
        **vital_values,
    )
    if recorded_at:
        vital_entry.recorded_at = recorded_at

    db.session.add(vital_entry)
    db.session.commit()
    return jsonify({"status": "success", "vital_id": vital_entry.id}), 201


@vitals_bp.route('/patient/<int:patient_id>/timeline', methods=['GET'])
@login_required
def patient_timeline(patient_id):
    if session.get('role') == 'patient' and session.get('user_id') != patient_id:
        return jsonify({"error": "Unauthorized"}), 403
    if session.get('role') == 'guest':
        patient = db.session.get(User, patient_id)
        if not patient or patient.role != 'patient':
            return jsonify({"error": "Patient not found"}), 404

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    date_str = request.args.get('date')

    try:
        if start_date_str or end_date_str:
            if not start_date_str or not end_date_str:
                return jsonify({"error": "Both start_date and end_date are required"}), 400
            start_date = date.fromisoformat(start_date_str)
            end_date = date.fromisoformat(end_date_str)
        else:
            target_date = date.fromisoformat(date_str) if date_str else datetime.utcnow().date()
            start_date = target_date
            end_date = target_date
    except ValueError:
        return jsonify({"error": "Dates must use YYYY-MM-DD format"}), 400

    if start_date > end_date:
        return jsonify({"error": "start_date must be on or before end_date"}), 400

    vitals, med_logs = get_patient_timeline_for_range(patient_id, start_date, end_date)

    return jsonify({
        "vitals": [
            {
                "id": v.id,
                "recorded_at": v.recorded_at.isoformat(),
                "systolic": v.systolic_bp,
                "diastolic": v.diastolic_bp,
                "heart_rate": v.heart_rate,
                "blood_sugar": v.blood_sugar,
                "weight_kg": v.weight_kg,
            } for v in vitals
        ],
        "medications": [
            {
                "id": m.id,
                "administered_at": m.administered_at.isoformat(),
                "status": m.status,
                "drug_name": m.prescription_item.drug_name
            } for m in med_logs
        ]
    })