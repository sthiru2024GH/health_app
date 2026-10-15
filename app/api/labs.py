from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, session
from app import db
from app.models import LabReport, LabParameter, User
from app.utils.decorators import login_required, require_role

labs_bp = Blueprint('labs', __name__)

@labs_bp.route('/report', methods=['POST'])
@login_required
def create_report():
    data = request.json
    
    if not data or not all(k in data for k in ('patient_id', 'test_name', 'parameters')):
        return jsonify({"error": "Missing required fields"}), 400
        
    # Security: Patient can only log their own reports, or doctor logs it
    current_user_id = session.get('user_id')
    current_user_role = session.get('role')
    
    if current_user_role == 'patient' and current_user_id != data['patient_id']:
        return jsonify({"error": "Unauthorized"}), 403

    recorded_at = None
    if 'recorded_at' in data and data['recorded_at']:
        try:
            recorded_at = datetime.fromisoformat(data['recorded_at'])
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    report_kwargs = {
        'patient_id': data['patient_id'],
        'test_name': data['test_name'],
        'doctor_notes': data.get('doctor_notes', '')
    }
    if recorded_at:
        report_kwargs['recorded_at'] = recorded_at

    report = LabReport(**report_kwargs)
    db.session.add(report)
    db.session.flush() # To get the report.id

    for param in data['parameters']:
        p = LabParameter(
            report_id=report.id,
            parameter_name=param['name'],
            value=float(param['value']),
            unit=param.get('unit', '')
        )
        db.session.add(p)

    db.session.commit()
    return jsonify({"message": "Lab report created", "report_id": report.id}), 201

@labs_bp.route('/patient/<int:patient_id>', methods=['GET'])
@login_required
def get_reports(patient_id):
    current_user_role = session.get('role')
    current_user_id = session.get('user_id')
    
    if current_user_role == 'patient' and current_user_id != patient_id:
        return jsonify({"error": "Unauthorized"}), 403
        
    reports = LabReport.query.filter_by(patient_id=patient_id).order_by(LabReport.recorded_at.desc()).all()
    
    result = []
    for r in reports:
        result.append({
            "id": r.id,
            "test_name": r.test_name,
            "recorded_at": r.recorded_at.isoformat(),
            "doctor_notes": r.doctor_notes,
            "parameters": [
                {"name": p.parameter_name, "value": p.value, "unit": p.unit} 
                for p in r.parameters
            ]
        })
        
    return jsonify({"reports": result}), 200

@labs_bp.route('/parameters/unique', methods=['GET'])
@login_required
def get_unique_parameters():
    # Get all distinct parameter names across all patients, ordered alphabetically
    unique_params = db.session.query(LabParameter.parameter_name)\
        .distinct()\
        .order_by(LabParameter.parameter_name.asc())\
        .all()
    param_list = [p[0] for p in unique_params]
    return jsonify({"parameters": param_list}), 200
