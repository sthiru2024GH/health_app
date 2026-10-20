import random
from datetime import datetime, timedelta, timezone, time
from app import create_app, db
from app.models import User, VitalSign, Practitioner, Prescription, PrescriptionItem, LabReport, LabParameter

app = create_app()
with app.app_context():
    print("Starting database seed...")
    
    # 1. Create User
    user = User.query.filter_by(username='testuser').first()
    if not user:
        user = User(username='testuser', name='John Doe', role='patient')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
    
    patient_id = user.id
    
    # 2. Add Practitioners
    p1 = Practitioner(patient_id=patient_id, name="Dr. Sarah Smith", specialization="Cardiologist", medical_practice="Allopathy")
    p2 = Practitioner(patient_id=patient_id, name="Dr. Anil Kumar", specialization="General Physician", medical_practice="Ayurvedic")
    db.session.add_all([p1, p2])
    db.session.flush()

    # 3. Add Prescriptions & Items
    presc1 = Prescription(patient_id=patient_id, practitioner_id=p1.id, date_issued=datetime.now(timezone.utc).date() - timedelta(days=30), notes="Take with plenty of water")
    db.session.add(presc1)
    db.session.flush()

    items = [
        PrescriptionItem(prescription_id=presc1.id, drug_name="Atorvastatin", quantity=1, unit="pill", time_of_day=time(8, 0), dependent_event="After Meal"),
        PrescriptionItem(prescription_id=presc1.id, drug_name="Metoprolol", quantity=0.5, unit="pill", time_of_day=time(20, 0), dependent_event="Independent")
    ]
    db.session.add_all(items)
    
    # 4. Generate 14 days of Vitals
    base_date = datetime.now(timezone.utc) - timedelta(days=14)
    vitals = []
    for i in range(14):
        rec_time = base_date + timedelta(days=i, hours=random.randint(8, 10))
        sys = random.randint(115, 135)
        dia = random.randint(75, 85)
        hr = random.randint(65, 80)
        sugar = round(random.uniform(90.0, 110.0), 1)
        vitals.append(VitalSign(patient_id=patient_id, recorded_at=rec_time, systolic_bp=sys, diastolic_bp=dia, heart_rate=hr, blood_sugar=sugar))
    db.session.add_all(vitals)

    # 5. Generate 4 months of Lab Reports
    lab_dates = [base_date - timedelta(days=120), base_date - timedelta(days=90), base_date - timedelta(days=60), base_date - timedelta(days=30)]
    for ld in lab_dates:
        report = LabReport(patient_id=patient_id, test_name="Lipid Profile", recorded_at=ld)
        db.session.add(report)
        db.session.flush()
        
        ldl_val = round(random.uniform(90.0, 140.0), 1)
        hdl_val = round(random.uniform(40.0, 60.0), 1)
        
        db.session.add_all([
            LabParameter(report_id=report.id, parameter_name="LDL Cholesterol", value=ldl_val, unit="mg/dL"),
            LabParameter(report_id=report.id, parameter_name="HDL Cholesterol", value=hdl_val, unit="mg/dL")
        ])

    db.session.commit()
    print("Successfully seeded the database with rich test data!")
