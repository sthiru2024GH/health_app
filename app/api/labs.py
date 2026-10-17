from datetime import datetime, timezone
from math import isfinite
from flask import Blueprint, request, jsonify, session
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import (
    LabReport,
    LabParameter,
    MasterLabTest,
    MasterLabParameter,
    User,
)
from app.utils.decorators import login_required, require_role

labs_bp = Blueprint('labs', __name__)


def _master_test_payload(data):
    if not isinstance(data, dict):
        return None, "A JSON object is required."

    name = data.get("name")
    parameters = data.get("parameters")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 150:
        return None, "Test name must contain 1 to 150 characters."
    if not isinstance(parameters, list) or not parameters:
        return None, "Add at least one health parameter."

    normalized_parameters = []
    seen_names = set()
    for parameter in parameters:
        if not isinstance(parameter, dict):
            return None, "Each parameter must be an object."

        parameter_name = parameter.get("name")
        unit = parameter.get("unit", "")
        if (
            not isinstance(parameter_name, str)
            or not parameter_name.strip()
            or len(parameter_name.strip()) > 100
        ):
            return None, "Parameter name must contain 1 to 100 characters."
        if not isinstance(unit, str) or len(unit.strip()) > 50:
            return None, "Unit of measure must be 50 characters or fewer."

        normalized_name = parameter_name.strip()
        if normalized_name.casefold() in seen_names:
            return None, f"Duplicate parameter name: {normalized_name}."
        seen_names.add(normalized_name.casefold())

        ranges = {}
        for key in ("low_range", "high_range"):
            raw_value = parameter.get(key)
            if raw_value in (None, ""):
                ranges[key] = None
                continue
            if isinstance(raw_value, bool):
                return None, f"{key.replace('_', ' ').capitalize()} must be numeric."
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                return None, f"{key.replace('_', ' ').capitalize()} must be numeric."
            if not isfinite(numeric_value):
                return None, f"{key.replace('_', ' ').capitalize()} must be finite."
            ranges[key] = numeric_value

        if (
            ranges["low_range"] is not None
            and ranges["high_range"] is not None
            and ranges["low_range"] > ranges["high_range"]
        ):
            return None, f"Low range cannot exceed high range for {normalized_name}."

        normalized_parameters.append({
            "name": normalized_name,
            "unit": unit.strip(),
            **ranges,
        })

    return {
        "name": name.strip(),
        "parameters": normalized_parameters,
    }, None


def _add_master_parameters(test, parameters):
    existing_parameters = {
        parameter.name.casefold(): parameter
        for parameter in test.parameters
    }
    updated_parameters = []
    for parameter in parameters:
        existing = existing_parameters.pop(parameter["name"].casefold(), None)
        if existing is None:
            existing = MasterLabParameter()
        existing.name = parameter["name"]
        existing.unit = parameter["unit"]
        existing.low_range = parameter["low_range"]
        existing.high_range = parameter["high_range"]
        updated_parameters.append(existing)
    test.parameters = updated_parameters


def _serialize_master_test(test):
    return {
        "id": test.id,
        "name": test.name,
        "parameters": [
            {
                "id": parameter.id,
                "name": parameter.name,
                "unit": parameter.unit,
                "low_range": parameter.low_range,
                "high_range": parameter.high_range,
            }
            for parameter in test.parameters
        ],
    }


@labs_bp.route('/master/tests', methods=['GET'])
@login_required
def get_master_tests():
    tests = MasterLabTest.query.order_by(MasterLabTest.name.asc()).all()
    return jsonify({"tests": [_serialize_master_test(test) for test in tests]}), 200


@labs_bp.route('/master/tests', methods=['POST'])
@login_required
def create_master_test():
    payload, error = _master_test_payload(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    existing = MasterLabTest.query.filter(
        db.func.lower(MasterLabTest.name) == payload["name"].casefold()
    ).first()
    if existing:
        return jsonify({"error": "A test with this name already exists."}), 409

    test = MasterLabTest(name=payload["name"])
    _add_master_parameters(test, payload["parameters"])
    db.session.add(test)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A test with this name already exists."}), 409

    return jsonify({"test": _serialize_master_test(test)}), 201


@labs_bp.route('/master/tests/<int:test_id>', methods=['PUT'])
@login_required
def update_master_test(test_id):
    test = db.session.get(MasterLabTest, test_id)
    if not test:
        return jsonify({"error": "Master lab test not found."}), 404

    payload, error = _master_test_payload(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    duplicate = MasterLabTest.query.filter(
        db.func.lower(MasterLabTest.name) == payload["name"].casefold(),
        MasterLabTest.id != test.id,
    ).first()
    if duplicate:
        return jsonify({"error": "A test with this name already exists."}), 409

    test.name = payload["name"]
    _add_master_parameters(test, payload["parameters"])
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A test with this name already exists."}), 409

    return jsonify({"test": _serialize_master_test(test)}), 200


@labs_bp.route('/master/tests/<int:test_id>', methods=['DELETE'])
@login_required
def delete_master_test(test_id):
    test = db.session.get(MasterLabTest, test_id)
    if not test:
        return jsonify({"error": "Master lab test not found."}), 404

    db.session.delete(test)
    db.session.commit()
    return jsonify({"message": "Master lab test deleted."}), 200


@labs_bp.route('/report', methods=['POST'])
@login_required
def create_report():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not all(
        key in data for key in ('patient_id', 'test_id', 'parameters')
    ):
        return jsonify({"error": "Missing required fields"}), 400

    patient_id = data.get("patient_id")
    test_id = data.get("test_id")
    parameters = data.get("parameters")
    if (
        isinstance(patient_id, bool)
        or not isinstance(patient_id, int)
        or isinstance(test_id, bool)
        or not isinstance(test_id, int)
        or not isinstance(parameters, list)
        or not parameters
    ):
        return jsonify({"error": "Invalid patient, test, or parameter data."}), 400

    # Security: Patient can only log their own reports, or doctor logs it
    current_user_id = session.get('user_id')
    current_user_role = session.get('role')
    if current_user_role == 'patient' and current_user_id != patient_id:
        return jsonify({"error": "Unauthorized"}), 403

    test = db.session.get(MasterLabTest, test_id)
    if not test:
        return jsonify({"error": "Select a valid master lab test."}), 400

    master_parameters = {parameter.id: parameter for parameter in test.parameters}
    report_parameters = []
    submitted_parameter_ids = set()
    for parameter in parameters:
        if not isinstance(parameter, dict):
            return jsonify({"error": "Invalid lab parameter data."}), 400
        parameter_id = parameter.get("master_parameter_id")
        value = parameter.get("value")
        if (
            isinstance(parameter_id, bool)
            or not isinstance(parameter_id, int)
            or parameter_id not in master_parameters
            or parameter_id in submitted_parameter_ids
            or isinstance(value, bool)
        ):
            return jsonify({"error": "Select a valid parameter and enter its value."}), 400
        submitted_parameter_ids.add(parameter_id)
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return jsonify({"error": "Parameter values must be numeric."}), 400
        if not isfinite(numeric_value):
            return jsonify({"error": "Parameter values must be finite numbers."}), 400
        master_parameter = master_parameters[parameter_id]
        report_parameters.append({
            "name": master_parameter.name,
            "value": numeric_value,
            "unit": master_parameter.unit,
        })

    recorded_at = None
    if 'recorded_at' in data and data['recorded_at']:
        try:
            recorded_at = datetime.fromisoformat(data['recorded_at'])
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    report_kwargs = {
        'patient_id': patient_id,
        'test_name': test.name,
        'doctor_notes': data.get('doctor_notes', '')
    }
    if recorded_at:
        report_kwargs['recorded_at'] = recorded_at

    report = LabReport(**report_kwargs)
    db.session.add(report)
    db.session.flush() # To get the report.id

    for param in report_parameters:
        p = LabParameter(
            report_id=report.id,
            parameter_name=param["name"],
            value=param["value"],
            unit=param["unit"],
        )
        db.session.add(p)

    db.session.commit()
    return jsonify({"message": "Lab report created", "report_id": report.id}), 201


@labs_bp.route('/report/<int:report_id>', methods=['PUT'])
@login_required
def update_report(report_id):
    report = db.session.get(LabReport, report_id)
    if not report:
        return jsonify({"error": "Lab report not found."}), 404

    if session.get('role') == 'patient' and session.get('user_id') != report.patient_id:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    test_id = data.get("test_id")
    parameters = data.get("parameters")
    if (
        isinstance(test_id, bool)
        or not isinstance(test_id, int)
        or not isinstance(parameters, list)
        or not parameters
    ):
        return jsonify({"error": "Select a test and enter at least one parameter value."}), 400

    test = db.session.get(MasterLabTest, test_id)
    if not test or test.name.casefold() != report.test_name.casefold():
        return jsonify({"error": "The selected test does not match this lab report."}), 400

    master_parameters = {parameter.id: parameter for parameter in test.parameters}
    submitted_parameters = {}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            return jsonify({"error": "Invalid lab parameter data."}), 400
        parameter_id = parameter.get("master_parameter_id")
        value = parameter.get("value")
        if (
            isinstance(parameter_id, bool)
            or not isinstance(parameter_id, int)
            or parameter_id not in master_parameters
            or parameter_id in submitted_parameters
            or isinstance(value, bool)
        ):
            return jsonify({"error": "Select a valid parameter and enter its value."}), 400
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return jsonify({"error": "Parameter values must be numeric."}), 400
        if not isfinite(numeric_value):
            return jsonify({"error": "Parameter values must be finite numbers."}), 400
        submitted_parameters[parameter_id] = numeric_value

    recorded_at = None
    if "recorded_at" in data:
        try:
            recorded_at = datetime.fromisoformat(data["recorded_at"])
        except (TypeError, ValueError):
            return jsonify({"error": "Recorded date and time must be valid."}), 400
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)

    existing_parameters = {
        parameter.parameter_name.casefold(): parameter
        for parameter in report.parameters.all()
    }
    for parameter_id, value in submitted_parameters.items():
        master_parameter = master_parameters[parameter_id]
        existing = existing_parameters.get(master_parameter.name.casefold())
        if existing:
            existing.value = value
            existing.unit = master_parameter.unit
        else:
            report.parameters.append(LabParameter(
                parameter_name=master_parameter.name,
                value=value,
                unit=master_parameter.unit,
            ))

    if recorded_at:
        report.recorded_at = recorded_at

    db.session.commit()
    return jsonify({"message": "Lab report updated", "report_id": report.id}), 200


@labs_bp.route('/patient/<int:patient_id>', methods=['GET'])
@login_required
def get_reports(patient_id):
    current_user_role = session.get('role')
    current_user_id = session.get('user_id')
    
    if current_user_role == 'patient' and current_user_id != patient_id:
        return jsonify({"error": "Unauthorized"}), 403
    if current_user_role == 'guest':
        patient = db.session.get(User, patient_id)
        if not patient or patient.role != 'patient':
            return jsonify({"error": "Patient not found"}), 404
        
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
    query = db.session.query(LabParameter.parameter_name).distinct()
    if session.get('role') == 'guest':
        try:
            patient_id = int(request.args.get('patient_id', ''))
        except ValueError:
            return jsonify({"error": "Select a patient to view lab analytics"}), 400
        patient = db.session.get(User, patient_id)
        if not patient or patient.role != 'patient':
            return jsonify({"error": "Patient not found"}), 404
        query = query.join(LabReport).filter(LabReport.patient_id == patient_id)

    unique_params = query.order_by(LabParameter.parameter_name.asc()).all()
    param_list = [p[0] for p in unique_params]
    return jsonify({"parameters": param_list}), 200
