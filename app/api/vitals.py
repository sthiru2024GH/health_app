# app/api/vitals.py
from datetime import date, datetime
from flask import Blueprint, request, jsonify, session
from app import db
from app.models import VitalSign, MedicationLog, PrescriptionItem
from app.services.patient_service import get_patient_timeline_for_range
from app.utils.decorators import login_required, require_role

vitals_bp = Blueprint('vitals', __name__)

@vitals_bp.route('/record', methods=['POST'])
@login_required
def record_vitals():
    data = request.json
    
    med_log_id = None
    if 'medication_schedule_id' in data:
        item = PrescriptionItem.query.get(data['medication_schedule_id'])
        if not item:
            return jsonify({"error": "Prescription Item not found"}), 404
        if session.get('role') == 'patient' and item.prescription.patient_id != session.get('user_id'):
            return jsonify({"error": "Unauthorized"}), 403
        med_log = MedicationLog(
            prescription_item_id=item.id,
            status=data.get('med_status', 'taken')
        )
        db.session.add(med_log)
        db.session.flush()
        med_log_id = med_log.id

    recorded_at = None
    if 'recorded_at' in data:
        # Datetime-local inputs usually give 'YYYY-MM-DDTHH:MM'
        try:
            recorded_at = datetime.fromisoformat(data['recorded_at'])
            # Ensure it is timezone aware if needed, or naive assuming UTC
            if recorded_at.tzinfo is None:
                from datetime import timezone
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    vital_kwargs = {
        'patient_id': data['patient_id'],
        'systolic_bp': data.get('systolic'),
        'diastolic_bp': data.get('diastolic'),
        'heart_rate': data.get('heart_rate'),
        'blood_sugar': data.get('blood_sugar'),
        'medication_log_id': med_log_id
    }

    if recorded_at:
        vital_kwargs['recorded_at'] = recorded_at

    vital_entry = VitalSign(**vital_kwargs)
    
    db.session.add(vital_entry)
    db.session.commit()

    return jsonify({"status": "success", "vital_id": vital_entry.id}), 201

@vitals_bp.route('/patient/<int:patient_id>/timeline', methods=['GET'])
@login_required
def patient_timeline(patient_id):
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
                "blood_sugar": v.blood_sugar
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