from datetime import datetime, timezone
from app import db

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    
    vitals = db.relationship('VitalSign', backref='patient', lazy='dynamic')
    schedules = db.relationship('MedicationSchedule', backref='patient', lazy='dynamic')

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
    
    medication_log_id = db.Column(db.Integer, db.ForeignKey('medication_logs.id'), nullable=True)

class MedicationSchedule(db.Model):
    __tablename__ = 'medication_schedules'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    medication_name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50), nullable=False)
    scheduled_time = db.Column(db.Time, nullable=False)
    instructions = db.Column(db.String(50))

class MedicationLog(db.Model):
    __tablename__ = 'medication_logs'
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('medication_schedules.id'), nullable=False)
    administered_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    status = db.Column(db.String(20), default='taken')
    
    vitals = db.relationship('VitalSign', backref='medication_log', uselist=False)