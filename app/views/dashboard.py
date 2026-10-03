# app/api/vitals.py
from datetime import datetime
from flask import Blueprint, jsonify, request
from app.services.patient_service import get_daily_patient_timeline

vitals_bp = Blueprint('vitals', __name__)

@vitals_bp.route('/patient/<int:patient_id>/timeline', methods=['GET'])
def patient_timeline(patient_id):
    # Parse query parameter (e.g. /patient/1/timeline?date=2026-10-03)
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