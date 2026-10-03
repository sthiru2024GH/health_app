# app/api/vitals.py
from datetime import datetime
from flask import Blueprint, request, jsonify
from app import db
from app.models import VitalSign, MedicationLog
from app.services.patient_service import get_daily_patient_timeline

vitals_bp = Blueprint('vitals', __name__)

@vitals_bp.route('/record', methods=['POST'])
def record_vitals():
    data = request.json
    
    med_log_id = None
    if 'medication_schedule_id' in data:
        med_log = MedicationLog(
            schedule_id=data['medication_schedule_id'],
            status=data.get('med_status', 'taken')
        )
        db.session.add(med_log)
        db.session.flush()
        med_log_id = med_log.id

    vital_entry = VitalSign(
        patient_id=data['patient_id'],
        systolic_bp=data.get('systolic'),
        diastolic_bp=data.get('diastolic'),
        heart_rate=data.get('heart_rate'),
        blood_sugar=data.get('blood_sugar'),
        medication_log_id=med_log_id
    )
    
    db.session.add(vital_entry)
    db.session.commit()

    return jsonify({"status": "success", "vital_id": vital_entry.id}), 201

@vitals_bp.route('/patient/<int:patient_id>/timeline', methods=['GET'])
def patient_timeline(patient_id):
    date_str = request.args.get('date')
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()

    vitals, med_logs = get_daily_patient_timeline(patient_id, target_date)

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
                "status": m.status
            } for m in med_logs
        ]
    })