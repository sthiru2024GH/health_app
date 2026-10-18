import math
from datetime import date, datetime, time, timedelta, timezone
from flask import Blueprint, request, jsonify, session
from sqlalchemy.orm import joinedload
from app import db
from app.models import Practitioner, Prescription, PrescriptionItem, MedicationLog, User
from app.utils.decorators import login_required, require_role

medications_bp = Blueprint('medications', __name__)


def _latest_prescriptions_by_practitioner(prescriptions):
    latest = {}
    for prescription in prescriptions:
        key = prescription.practitioner_id
        current = latest.get(key)
        if current is None or (
            prescription.date_issued or date.min,
            prescription.id,
        ) > (
            current.date_issued or date.min,
            current.id,
        ):
            latest[key] = prescription
    return latest


def _patient_read_error(patient_id):
    role = session.get('role')
    if role == 'patient' and session.get('user_id') != patient_id:
        return jsonify({"error": "Unauthorized"}), 403
    if role == 'guest':
        patient = db.session.get(User, patient_id)
        if not patient or patient.role != 'patient':
            return jsonify({"error": "Patient not found"}), 404
    return None


# --- PRACTITIONERS ---
@medications_bp.route('/practitioner', methods=['POST'])
@login_required
def create_practitioner():
    data = request.json
    if not data or not data.get('patient_id') or not data.get('name'):
        return jsonify({"error": "Missing required fields"}), 400

    current_user_id = session.get('user_id')
    current_user_role = session.get('role')
    if current_user_role == 'patient' and current_user_id != data['patient_id']:
        return jsonify({"error": "Unauthorized"}), 403

    practitioner = Practitioner(
        patient_id=data['patient_id'],
        name=data['name'],
        specialization=data.get('specialization', ''),
        medical_practice=data.get('medical_practice', '')
    )
    db.session.add(practitioner)
    db.session.commit()
    return jsonify({"message": "Practitioner added", "id": practitioner.id}), 201

@medications_bp.route('/practitioners/patient/<int:patient_id>', methods=['GET'])
@login_required
def get_practitioners(patient_id):
    access_error = _patient_read_error(patient_id)
    if access_error:
        return access_error

    practitioners = Practitioner.query.filter_by(patient_id=patient_id).all()
    return jsonify({
        "practitioners": [
            {
                "id": p.id,
                "name": p.name,
                "specialization": p.specialization,
                "medical_practice": p.medical_practice
            } for p in practitioners
        ]
    }), 200


# --- PRESCRIPTIONS & MEDICATIONS ---
@medications_bp.route('/prescription', methods=['POST'])
@login_required
def create_prescription():
    data = request.json
    if not data or not data.get('patient_id'):
        return jsonify({"error": "Missing required fields"}), 400

    # Allow prescription with either items (medications) or notes (advice), but not neither
    items = data.get('items', [])
    notes = data.get('notes', '').strip()
    if not items and not notes:
        return jsonify({"error": "Prescription must include at least one medication or notes"}), 400

    current_user_id = session.get('user_id')
    current_user_role = session.get('role')
    if current_user_role == 'patient' and current_user_id != data['patient_id']:
        return jsonify({"error": "Unauthorized"}), 403

    prescription = Prescription(
        patient_id=data['patient_id'],
        practitioner_id=data.get('practitioner_id'),
        notes=notes
    )
    if data.get('date_issued'):
        prescription.date_issued = datetime.strptime(data['date_issued'], '%Y-%m-%d').date()

    db.session.add(prescription)
    db.session.flush()

    for item in items:
        scheduled_time = datetime.strptime(item['time_of_day'], '%H:%M').time()
        p_item = PrescriptionItem(
            prescription_id=prescription.id,
            drug_name=item['drug_name'],
            quantity=float(item['quantity']),
            unit=item['unit'],
            time_of_day=scheduled_time,
            dependent_event=item.get('dependent_event', 'Independent')
        )
        db.session.add(p_item)

    db.session.commit()
    return jsonify({"message": "Prescription created", "id": prescription.id}), 201

@medications_bp.route('/prescriptions/patient/<int:patient_id>', methods=['GET'])
@login_required
def get_prescriptions(patient_id):
    access_error = _patient_read_error(patient_id)
    if access_error:
        return access_error

    prescriptions = Prescription.query.filter_by(patient_id=patient_id).order_by(Prescription.date_issued.desc()).all()
    latest_by_practitioner = _latest_prescriptions_by_practitioner(prescriptions)

    result = []
    for p in prescriptions:
        patient = db.session.get(User, p.patient_id)
        practitioner = db.session.get(Practitioner, p.practitioner_id) if p.practitioner_id else None
        items = p.items.all()
        status = (
            "closed" if p.closed_at
            else "current" if latest_by_practitioner[p.practitioner_id].id == p.id
            else "superseded"
        )
        result.append({
            "id": p.id,
            "patient_id": p.patient_id,
            "patient_name": patient.name if patient else None,
            "practitioner_id": p.practitioner_id,
            "practitioner_name": practitioner.name if practitioner else None,
            "date_issued": p.date_issued.isoformat(),
            "notes": p.notes,
            "status": status,
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
            "items": [
                {
                    "id": item.id,
                    "drug_name": item.drug_name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "time_of_day": item.time_of_day.strftime('%H:%M'),
                    "dependent_event": item.dependent_event,
                    "has_logs": MedicationLog.query.filter_by(prescription_item_id=item.id).first() is not None
                } for item in items
            ]
        })
    return jsonify({"prescriptions": result}), 200


@medications_bp.route('/prescription/<int:prescription_id>', methods=['PUT'])
@login_required
def update_prescription(prescription_id):
    prescription = db.session.get(Prescription, prescription_id)
    if not prescription:
        return jsonify({"error": "Prescription not found"}), 404

    if session.get('role') == 'patient' and prescription.patient_id != session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403
    if prescription.closed_at:
        return jsonify({"error": "A force-closed prescription cannot be edited."}), 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data.get('date_issued'):
        return jsonify({"error": "Date issued is required"}), 400

    # Allow prescription with either items (medications) or notes (advice), but not neither
    items = data.get('items', []) if isinstance(data.get('items'), list) else []
    notes = (data.get('notes', '') or '').strip()
    if not items and not notes:
        return jsonify({"error": "Prescription must include at least one medication or notes"}), 400

    try:
        date_issued = datetime.strptime(data['date_issued'], '%Y-%m-%d').date()
        if not isinstance(notes, str):
            return jsonify({"error": "Prescription notes must be text"}), 400

        submitted_items = []
        submitted_ids = set()
        for item in items:
            if not isinstance(item, dict):
                return jsonify({"error": "Each medication must include a name, quantity, unit, and time"}), 400

            drug_name = item.get('drug_name')
            unit = item.get('unit')
            time_of_day = item.get('time_of_day')
            if (
                not isinstance(drug_name, str) or not drug_name.strip()
                or not isinstance(unit, str) or not unit.strip()
                or not isinstance(time_of_day, str) or not time_of_day
                or not item.get('quantity')
            ):
                return jsonify({"error": "Each medication must include a name, quantity, unit, and time"}), 400

            quantity = float(item['quantity'])
            if not math.isfinite(quantity) or quantity <= 0:
                return jsonify({"error": "Medication quantity must be a finite number greater than zero"}), 400

            scheduled_time = datetime.strptime(time_of_day, '%H:%M').time()
            item_id = item.get('id')
            if item_id is not None:
                item_id = int(item_id)
                if item_id in submitted_ids:
                    return jsonify({"error": "A medication was submitted more than once"}), 400
                submitted_ids.add(item_id)

            submitted_items.append({
                "id": item_id,
                "drug_name": drug_name.strip(),
                "quantity": quantity,
                "unit": unit.strip(),
                "time_of_day": scheduled_time,
                "dependent_event": item.get('dependent_event', 'Independent')
            })
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid prescription date, quantity, or medication time"}), 400

    practitioner_id = data.get('practitioner_id')
    if practitioner_id in ('', None):
        practitioner_id = None
    else:
        try:
            practitioner_id = int(practitioner_id)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid practitioner"}), 400
        practitioner = db.session.get(Practitioner, practitioner_id)
        if not practitioner or practitioner.patient_id != prescription.patient_id:
            return jsonify({"error": "Practitioner not found for this patient"}), 400

    existing_items = {item.id: item for item in prescription.items.all()}
    if any(item["id"] is not None and item["id"] not in existing_items for item in submitted_items):
        return jsonify({"error": "Medication does not belong to this prescription"}), 400

    submitted_existing_ids = {
        item["id"] for item in submitted_items if item["id"] is not None
    }
    for item_id, existing_item in existing_items.items():
        has_logs = MedicationLog.query.filter_by(prescription_item_id=item_id).first() is not None
        submitted_item = next(
            (item for item in submitted_items if item["id"] == item_id),
            None,
        )
        if has_logs and submitted_item is None:
            return jsonify({"error": "Medications with recorded history cannot be removed"}), 409
        if has_logs and (
            existing_item.drug_name != submitted_item["drug_name"]
            or existing_item.quantity != submitted_item["quantity"]
            or existing_item.unit != submitted_item["unit"]
            or existing_item.time_of_day != submitted_item["time_of_day"]
            or existing_item.dependent_event != submitted_item["dependent_event"]
        ):
            return jsonify({"error": "Medication details with recorded history cannot be changed"}), 409

    prescription.date_issued = date_issued
    prescription.practitioner_id = practitioner_id
    prescription.notes = notes

    for item_id, existing_item in existing_items.items():
        if item_id not in submitted_existing_ids:
            db.session.delete(existing_item)

    for item_data in submitted_items:
        item_id = item_data.pop("id")
        if item_id is None:
            db.session.add(PrescriptionItem(
                prescription_id=prescription.id,
                **item_data,
            ))
        else:
            existing_item = existing_items[item_id]
            for field, value in item_data.items():
                setattr(existing_item, field, value)

    db.session.commit()
    return jsonify({"message": "Prescription updated"}), 200


@medications_bp.route('/prescription/<int:prescription_id>/close', methods=['POST'])
@login_required
def force_close_prescription(prescription_id):
    prescription = db.session.get(Prescription, prescription_id)
    if not prescription:
        return jsonify({"error": "Prescription not found"}), 404

    if session.get('role') == 'patient' and prescription.patient_id != session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403

    if prescription.closed_at:
        return jsonify({
            "message": "Prescription is already force-closed.",
            "closed_at": prescription.closed_at.isoformat(),
        }), 200

    prescription.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({
        "message": "Prescription force-closed.",
        "closed_at": prescription.closed_at.isoformat(),
    }), 200


@medications_bp.route('/prescription/<int:prescription_id>', methods=['DELETE'])
@login_required
def delete_prescription(prescription_id):
    prescription = db.session.get(Prescription, prescription_id)
    if not prescription:
        return jsonify({"error": "Prescription not found"}), 404

    if session.get('role') == 'patient' and prescription.patient_id != session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403

    item_ids = [item.id for item in prescription.items.all()]
    if item_ids and MedicationLog.query.filter(
        MedicationLog.prescription_item_id.in_(item_ids)
    ).first():
        return jsonify({
            "error": "This prescription has medication history and cannot be deleted."
        }), 409

    db.session.delete(prescription)
    db.session.commit()
    return jsonify({"message": "Prescription deleted"}), 200

# Flattens all prescription items for the medication schedule view
@medications_bp.route('/schedule/patient/<int:patient_id>', methods=['GET'])
@login_required
def get_patient_schedules(patient_id):
    access_error = _patient_read_error(patient_id)
    if access_error:
        return access_error

    today = datetime.now(timezone.utc).date()
    start_of_day = datetime.combine(today, time.min, tzinfo=timezone.utc)
    start_of_next_day = start_of_day + timedelta(days=1)
    taken_today = db.session.query(MedicationLog.id).filter(
        MedicationLog.prescription_item_id == PrescriptionItem.id,
        MedicationLog.status == 'taken',
        MedicationLog.administered_at >= start_of_day,
        MedicationLog.administered_at < start_of_next_day
    ).exists()

    prescriptions = Prescription.query.filter_by(patient_id=patient_id).all()
    latest_prescriptions = _latest_prescriptions_by_practitioner(prescriptions)
    active_prescription_ids = [
        prescription.id
        for prescription in latest_prescriptions.values()
        if not prescription.closed_at
    ]
    items = PrescriptionItem.query.filter(
        PrescriptionItem.prescription_id.in_(active_prescription_ids),
        ~taken_today,
    ).order_by(
        PrescriptionItem.time_of_day.asc(),
        PrescriptionItem.drug_name.asc(),
    ).all()
    schedules = [
        {
            "id": item.id,
            "drug_name": item.drug_name,
            "quantity": item.quantity,
            "unit": item.unit,
            "time_of_day": item.time_of_day.strftime('%H:%M'),
            "dependent_event": item.dependent_event
        }
        for item in items
    ]

    return jsonify({"schedules": schedules}), 200


@medications_bp.route('/logs/patient/<int:patient_id>', methods=['GET'])
@login_required
def get_patient_medication_logs(patient_id):
    access_error = _patient_read_error(patient_id)
    if access_error:
        return access_error

    date_str = request.args.get('date')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now(timezone.utc).date()
    except ValueError:
        return jsonify({"error": "Date must use YYYY-MM-DD format"}), 400

    start_of_day = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    start_of_next_day = start_of_day + timedelta(days=1)
    logs = MedicationLog.query.join(PrescriptionItem).join(Prescription).filter(
        Prescription.patient_id == patient_id,
        MedicationLog.administered_at >= start_of_day,
        MedicationLog.administered_at < start_of_next_day,
    ).options(joinedload(MedicationLog.prescription_item)).order_by(
        MedicationLog.administered_at.desc()
    ).all()

    return jsonify({
        "logs": [
            {
                "id": log.id,
                "drug_name": log.prescription_item.drug_name,
                "status": log.status,
                "administered_at": log.administered_at.isoformat(),
            }
            for log in logs
        ]
    }), 200


@medications_bp.route('/log', methods=['POST'])
@login_required
def log_medication():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or 'schedule_id' not in data:
        return jsonify({"error": "Missing schedule_id"}), 400

    schedule_id = data['schedule_id']
    if isinstance(schedule_id, bool) or not isinstance(schedule_id, int):
        return jsonify({"error": "schedule_id must be an integer"}), 400

    item = db.session.get(PrescriptionItem, schedule_id)
    if not item:
        return jsonify({"error": "Prescription Item not found"}), 404

    # Verify patient ownership via parent Prescription
    current_user_id = session.get('user_id')
    current_user_role = session.get('role')
    if current_user_role == 'patient' and current_user_id != item.prescription.patient_id:
        return jsonify({"error": "Unauthorized"}), 403

    prescription = Prescription.query.filter_by(
        id=item.prescription_id
    ).with_for_update().first()
    if not prescription or prescription.closed_at:
        return jsonify({"error": "This prescription is no longer active."}), 409

    current_prescriptions = Prescription.query.filter_by(
        patient_id=prescription.patient_id
    ).all()
    latest = _latest_prescriptions_by_practitioner(current_prescriptions)
    if latest[prescription.practitioner_id].id != prescription.id:
        return jsonify({"error": "This prescription has been superseded."}), 409

    administered_at = datetime.now(timezone.utc)
    if 'administered_at' in data and data['administered_at']:
        try:
            administered_at = datetime.fromisoformat(data['administered_at'])
            if administered_at.tzinfo is None:
                administered_at = administered_at.replace(tzinfo=timezone.utc)
            administered_at = administered_at.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return jsonify({"error": "administered_at must be a valid ISO datetime"}), 400

    status = data.get('status', 'taken')
    if status == 'taken':
        day_start = datetime.combine(
            administered_at.date(), time.min, tzinfo=timezone.utc
        )
        next_day = day_start + timedelta(days=1)
        existing_log = MedicationLog.query.filter(
            MedicationLog.prescription_item_id == item.id,
            MedicationLog.status == 'taken',
            MedicationLog.administered_at >= day_start,
            MedicationLog.administered_at < next_day,
        ).first()
        if existing_log:
            return jsonify({
                "message": "This medication has already been marked as taken for that date.",
                "log_id": existing_log.id,
                "already_recorded": True,
            }), 200

    log_kwargs = {
        'prescription_item_id': item.id,
        'status': status,
        'administered_at': administered_at,
    }

    log = MedicationLog(**log_kwargs)
    db.session.add(log)
    db.session.commit()

    return jsonify({"message": "Medication logged successfully", "log_id": log.id}), 201
