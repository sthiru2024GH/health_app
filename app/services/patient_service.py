from datetime import datetime, time
from app.models import VitalSign, MedicationLog, MedicationSchedule

def get_daily_patient_timeline(patient_id, target_date):
    start_dt = datetime.combine(target_date, time.min)
    end_dt = datetime.combine(target_date, time.max)
    
    # Fetch Vitals
    vitals = VitalSign.query.filter(
        VitalSign.patient_id == patient_id,
        VitalSign.recorded_at.between(start_dt, end_dt)
    ).order_by(VitalSign.recorded_at.asc()).all()

    # Fetch Medication Logs
    med_logs = MedicationLog.query.join(MedicationSchedule).filter(
        MedicationSchedule.patient_id == patient_id,
        MedicationLog.administered_at.between(start_dt, end_dt)
    ).order_by(MedicationLog.administered_at.asc()).all()

    return vitals, med_logs