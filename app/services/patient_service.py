from datetime import datetime, time, timedelta
from sqlalchemy.orm import joinedload
from app.models import VitalSign, MedicationLog, PrescriptionItem, Prescription


def get_daily_patient_timeline(patient_id, target_date):
    return get_patient_timeline_for_range(
        patient_id,
        target_date,
        target_date,
    )


def get_patient_timeline_for_range(patient_id, start_date, end_date):
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min)
    
    vitals = VitalSign.query.filter(
        VitalSign.patient_id == patient_id,
        VitalSign.recorded_at >= start_dt,
        VitalSign.recorded_at < end_dt,
    ).order_by(VitalSign.recorded_at.asc()).all()

    med_logs = MedicationLog.query.join(PrescriptionItem).join(Prescription).filter(
        Prescription.patient_id == patient_id,
        MedicationLog.administered_at >= start_dt,
        MedicationLog.administered_at < end_dt,
    ).options(joinedload(MedicationLog.prescription_item)).order_by(MedicationLog.administered_at.asc()).all()

    return vitals, med_logs