from datetime import datetime, timezone
from app import db

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='patient') # patient, doctor, caregiver, guest

    # Relationships
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    patients = db.relationship('User', backref=db.backref('doctor', remote_side=[id]))
    
    vitals = db.relationship('VitalSign', backref='patient', lazy='dynamic')
    practitioners = db.relationship('Practitioner', backref='patient', lazy='dynamic')
    prescriptions = db.relationship('Prescription', backref='patient', lazy='dynamic')
    symptoms = db.relationship('SymptomEntry', backref='patient', lazy='dynamic')

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return bool(self.password_hash) and check_password_hash(
            self.password_hash, password
        )


class LoginCaptcha(db.Model):
    __tablename__ = 'login_captchas'
    id = db.Column(db.String(32), primary_key=True)
    answer_digest = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.Integer, nullable=False, index=True)


class SymptomEntry(db.Model):
    __tablename__ = 'symptom_entries'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    recorded_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=False)


class Intervention(db.Model):
    __tablename__ = 'interventions'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    practitioner_id = db.Column(db.Integer, db.ForeignKey('practitioners.id'), nullable=False)
    symptom_id = db.Column(db.Integer, db.ForeignKey('symptom_entries.id'), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    medication_type = db.Column(db.String(20), nullable=True)
    drug_name = db.Column(db.String(150), nullable=True)
    frequency_count = db.Column(db.Integer, nullable=True)
    frequency_unit = db.Column(db.String(20), nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    practitioner = db.relationship('Practitioner')
    symptom = db.relationship('SymptomEntry')
    logs = db.relationship('InterventionLog', backref='intervention', lazy='dynamic', cascade='all, delete-orphan')


class InterventionLog(db.Model):
    __tablename__ = 'intervention_logs'
    id = db.Column(db.Integer, primary_key=True)
    intervention_id = db.Column(db.Integer, db.ForeignKey('interventions.id'), nullable=False, index=True)
    administered_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    notes = db.Column(db.Text, nullable=False, default='')


class VitalSign(db.Model):
    __tablename__ = 'vital_signs'
    id = db.Column(db.Integer, primary_key=True)  # Use Integer instead of BigInteger
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recorded_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    systolic_bp = db.Column(db.Integer, nullable=True)
    diastolic_bp = db.Column(db.Integer, nullable=True)
    heart_rate = db.Column(db.Integer, nullable=True)
    blood_sugar = db.Column(db.Float, nullable=True)
    temperature = db.Column(db.Float, nullable=True)
    weight_kg = db.Column(db.Float, nullable=True)
    
    medication_log_id = db.Column(db.Integer, db.ForeignKey('medication_logs.id'), nullable=True)

class Practitioner(db.Model):
    __tablename__ = 'practitioners'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    specialization = db.Column(db.String(100), nullable=True)
    medical_practice = db.Column(db.String(50), nullable=True) # Allopathy, Homeopathy, Ayurvedic

class Prescription(db.Model):
    __tablename__ = 'prescriptions'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    practitioner_id = db.Column(db.Integer, db.ForeignKey('practitioners.id'), nullable=True)
    date_issued = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    notes = db.Column(db.Text, nullable=True)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    items = db.relationship('PrescriptionItem', backref='prescription', lazy='dynamic', cascade="all, delete-orphan")

class PrescriptionItem(db.Model):
    __tablename__ = 'prescription_items'
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id'), nullable=False)
    drug_name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False) # e.g., pills, ml
    time_of_day = db.Column(db.Time, nullable=False)
    dependent_event = db.Column(db.String(50), nullable=True) # Before meal, After meal, Independent

class MedicationLog(db.Model):
    __tablename__ = 'medication_logs'
    id = db.Column(db.Integer, primary_key=True)
    prescription_item_id = db.Column(db.Integer, db.ForeignKey('prescription_items.id'), nullable=False)
    administered_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    status = db.Column(db.String(20), default='taken')
    
    prescription_item = db.relationship('PrescriptionItem', backref='medication_logs')
    vitals = db.relationship('VitalSign', backref='medication_log', uselist=False)

class LabReport(db.Model):
    __tablename__ = 'lab_reports'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    test_name = db.Column(db.String(150), nullable=False) # e.g., "Lipid Profile", "CBC"
    recorded_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    doctor_notes = db.Column(db.Text, nullable=True)

    parameters = db.relationship('LabParameter', backref='report', lazy='dynamic', cascade="all, delete-orphan")

class LabParameter(db.Model):
    __tablename__ = 'lab_parameters'
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('lab_reports.id'), nullable=False)
    parameter_name = db.Column(db.String(100), nullable=False) # e.g., "LDL Cholesterol"
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=True) # e.g., "mg/dL"

class MasterLabTest(db.Model):
    __tablename__ = 'master_lab_tests'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)

    parameters = db.relationship(
        'MasterLabParameter',
        backref='test',
        lazy='select',
        cascade='all, delete-orphan',
        order_by='MasterLabParameter.name',
    )

class MasterLabParameter(db.Model):
    __tablename__ = 'master_lab_parameters'
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('master_lab_tests.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(50), nullable=False, default='')
    low_range = db.Column(db.Float, nullable=True)
    high_range = db.Column(db.Float, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('test_id', 'name', name='uq_master_lab_parameter_test_name'),
    )