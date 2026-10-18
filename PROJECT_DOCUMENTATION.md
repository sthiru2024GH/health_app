# HealthApp Project Documentation

## 1. Application architecture

HealthApp is a Flask prototype for recording and viewing patient health
information. It is a server-rendered web application: Jinja templates provide
the pages, browser JavaScript calls JSON endpoints, and SQLAlchemy persists
accounts and health records in SQLite or PostgreSQL.

```text
Browser
  ├── HTML pages and static CSS  ──> Flask main blueprint ──> Jinja templates
  └── JSON requests              ──> Flask API blueprints ──> SQLAlchemy models
                                                              │
                                                              └── SQLite / PostgreSQL
```

### Main components

| Component | Responsibility |
| --- | --- |
| `run.py`, `wsgi.py` | Create the Flask application for local execution or a WSGI server. |
| `config.py` | Select development/production configuration and the database URI. |
| `app/__init__.py` | Initialize Flask extensions, create/migrate the schema, register blueprints, and enforce guest read-only requests. |
| `app/views/main.py` | Serve login, registration, and role-selected dashboard pages. |
| `app/api/` | Expose authentication and health-record JSON endpoints. |
| `app/models.py` | Define SQLAlchemy models and relationships for users and health records. |
| `app/services/patient_service.py` | Query a patient’s vital and medication timeline over a date range. |
| `app/utils/` | Provide login/role decorators and CAPTCHA challenge handling. |
| `app/templates/`, `app/static/` | Contain the Jinja pages and CSS. |
| `app/schema_migrations.py` | Apply compatibility migrations for legacy database schemas at startup. |

### Request and data flow

1. `create_app()` loads configuration and binds SQLAlchemy and Flask-Migrate.
2. The application imports its models, creates missing tables, and attempts
   legacy schema migrations.
3. Flask registers the page and API blueprints.
4. A browser page renders from a Jinja template. Page JavaScript sends
   same-origin JSON requests to the API.
5. API handlers validate inputs, check the session/role and relevant record
   ownership, use SQLAlchemy to read or write records, and return JSON.

## 2. Features and roles

- **Patient:** Registers or signs in, records symptoms, vitals, lab reports,
  medications, and interventions, and views their own records.
- **Doctor:** Can register and sign in. The current doctor dashboard is a
  prototype mock-up (including a hard-coded sample patient); it is not a
  functioning patient-management workflow.
- **Guest:** Not offered through public registration. Guest access is
  administrator-provisioned and read-only. Guests can list patients and view
  selected patient records. The application rejects non-read HTTP methods for
  guest sessions.

Session role checks and record-ownership checks are implemented in route
handlers and decorators. They are not a substitute for a comprehensive
production authorization policy: access rules differ between endpoint groups.
Review each route before exposing or extending access to health records.

### Health-record areas

- **Vitals and timeline:** Numeric readings, timestamps, and optional
  medication associations; timeline queries can cover one day or a date range.
- **Symptoms:** Patient-reported descriptions with a severity value.
- **Practitioners and prescriptions:** Patient-associated practitioners,
  prescription headers/items, scheduled doses, and medication logs.
- **Labs:** An editable master test/parameter catalog plus patient lab reports
  and measured parameters.
- **Interventions:** Plans connected to a practitioner and symptom, with
  optional medication details and dated administration logs.

## 3. API overview

All API routes are JSON endpoints. Blueprint prefixes are registered in
`app/__init__.py`.

| Prefix | Examples of routes | Purpose |
| --- | --- | --- |
| `/api/auth` | `POST /register`, `POST /login`, `POST /logout`, `GET /me`, `GET /captcha`, `GET /patients` | Registration, session authentication, CAPTCHA, and guest patient selection. |
| `/api/vitals` | `POST /record`, `GET /patient/<patient_id>/timeline` | Record readings and retrieve health timelines. |
| `/api/medications` | `POST /practitioner`, `POST /prescription`, `GET /prescriptions/patient/<patient_id>`, `GET /schedule/patient/<patient_id>`, `POST /log` | Practitioners, prescription management, schedules, and dose history. |
| `/api/labs` | `GET/POST /master/tests`, `PUT/DELETE /master/tests/<test_id>`, `POST /report`, `GET /patient/<patient_id>` | Maintain test definitions and manage/view lab reports. |
| `/api/symptoms` | `GET /`, `POST /` | Read symptom entries and record patient symptoms. |
| `/api/interventions` | `GET /`, `POST /`, `POST /<intervention_id>/logs`, `PUT /logs/<log_id>` | View and manage patient intervention plans and logs. |

For exact methods, payload validation, and response fields, the route handlers
in `app/api/` are the source of truth.

## 4. Data model

The main relationships are:

```text
User (patient)
 ├── VitalSign ── optional MedicationLog
 ├── SymptomEntry ── Intervention ── InterventionLog
 ├── Practitioner ── Prescription ── PrescriptionItem ── MedicationLog
 └── LabReport ── LabParameter

MasterLabTest ── MasterLabParameter
User.doctor_id ──> User.id
```

`app/models.py` defines the ORM schema. `PRODUCTION_SCHEMA.txt` contains a
PostgreSQL-oriented reference derived from those models; it is not a dump or
guarantee of the live database schema. The legacy migration preserves existing
medication-log IDs while associating logs with prescription items, and avoids
guessing when legacy data is ambiguous.

## 5. Setup and operation

### Requirements

- Python version compatible with the pinned packages in `requirements.txt`.
- SQLite for a local database by default, or PostgreSQL with the
  `psycopg2-binary` driver.

### Install and run locally

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The local entry point runs Flask with debug enabled. The default database URI
is `sqlite:///app.db`; the application also creates the configured `instance`
directory. `init_db.py` is available to initialize tables explicitly.

### Configuration

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs Flask session cookies and protects CAPTCHA answer digests. Supply a strong, private value outside local development. |
| `DATABASE_URL` | SQLAlchemy database connection URL. If unset, the app uses SQLite. |

`config.py` defines development and production configuration classes. The
`default` configuration currently maps to development; verify the selected
configuration and `DEBUG` setting in a deployment. `render.yaml` installs
`requirements.txt` and starts `gunicorn wsgi:app`.

### Tests and checks

No test suite, lint configuration, or build command is defined in the repository
at the time of writing. After changing behavior, manually verify affected
browser flows and API routes against a disposable database.

## 6. Deployment and operational notes

- This project describes itself as a prototype. It is not represented as
  production-ready or as a substitute for clinical systems.
- Health records are sensitive. Before real deployment, review authentication,
  authorization, audit logging, encryption, backups, retention, privacy, and
  applicable regulatory obligations.
- Configure a strong `SECRET_KEY` and a protected production database URL using
  the hosting provider’s secret/environment settings. Do not commit credentials.
- Application startup calls `db.create_all()` and performs legacy migrations.
  Back up production data and validate the migrated schema before deployment.
- `PRODUCTION_SCHEMA.txt` documents an intended schema, not the state of any
  particular live database.

## 7. Annotated code dump: core excerpts

These excerpts illustrate the application’s main control points; they are
intentionally not a duplicate dump of every source file. The repository source
files linked above remain authoritative.

### Application factory — `app/__init__.py`

```python
db = SQLAlchemy()  # Define the extension once; bind it to each app in the factory.
migrate = Migrate()

def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])  # Load the selected environment settings.

    db.init_app(app)  # Bind database access to this Flask application.
    migrate.init_app(app, db)

    with app.app_context():
        from app import models  # Register model metadata before creating tables.
        db.create_all()
        from app.schema_migrations import migrate_legacy_schema
        migrate_legacy_schema(db.engine, app.logger)  # Bring supported legacy schemas forward.

    # API and page blueprints keep route groups separate.
    app.register_blueprint(vitals_bp, url_prefix="/api/vitals")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(main_bp)

    @app.before_request
    def enforce_guest_read_only():
        # Reject state-changing requests from guest sessions before route handling.
        if (
            session.get("role") == "guest"
            and request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.endpoint != "auth.logout"
        ):
            return jsonify({"error": "Guest accounts have read-only access."}), 403

    return app
```

The production factory registers all API blueprints; only representative
registrations are shown above.

### Authentication — `app/api/auth.py`

```python
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"error": "Missing username or password"}), 400

    # A valid, single-use CAPTCHA is required before checking credentials.
    if not verify_login_captcha(data.get('captcha_answer')):
        return jsonify({"error": "Please solve the CAPTCHA to continue."}), 400

    user = User.query.filter_by(username=data['username']).first()
    if user and user.check_password(data['password']):
        session.clear()  # Discard stale session state on successful sign-in.
        session['user_id'] = user.id
        session['role'] = user.role
        session['name'] = user.name
        return jsonify({"message": "Login successful"}), 200

    return jsonify({"error": "Invalid username or password"}), 401
```

The actual success response also includes basic user details. Passwords are
stored as Werkzeug password hashes by the `User` model.

### ORM model — `app/models.py`

```python
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='patient')

    # The self-reference associates patient accounts with a doctor account.
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    patients = db.relationship(
        'User', backref=db.backref('doctor', remote_side=[id])
    )

    # Health records point back to their owning patient.
    vitals = db.relationship('VitalSign', backref='patient', lazy='dynamic')
    prescriptions = db.relationship('Prescription', backref='patient', lazy='dynamic')

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)  # Never persist plaintext.
```

Additional model classes represent symptoms, interventions, medication history,
laboratory reports, and the master laboratory catalog.

### Example patient endpoint — `app/api/symptoms.py`

```python
@symptoms_bp.route('', methods=['POST'])
@require_role('patient')  # Require an authenticated patient, not a guest or doctor.
def create_symptom():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A valid symptom entry is required'}), 400

    # Validate required fields and restrict severity to the supported values.
    if not data.get('recorded_at') or not data.get('severity'):
        return jsonify({'error': 'Date and severity are required'}), 400
    if data['severity'] not in SEVERITIES:
        return jsonify({'error': 'Invalid severity'}), 400

    recorded_at = datetime.fromisoformat(data['recorded_at'])
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)  # Normalize naive input.

    entry = SymptomEntry(
        patient_id=session['user_id'],  # Derive ownership from the signed-in session.
        recorded_at=recorded_at,
        severity=data['severity'],
        description=data['description'].strip(),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'message': 'Symptom recorded', 'id': entry.id}), 201
```

This shortened excerpt omits some required-field and timestamp error handling
present in the complete route.
