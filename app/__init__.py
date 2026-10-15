from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config

# Instantiate extensions
db = SQLAlchemy()
migrate = Migrate()

def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Bind SQLAlchemy to this app instance
    db.init_app(app)
    migrate.init_app(app, db)

    # Import models within app context so SQLAlchemy registers them
    with app.app_context():
        from app import models
        db.create_all()

    # Register blueprints
    from app.api.vitals import vitals_bp
    from app.api.auth import auth_bp
    from app.api.medications import medications_bp
    from app.api.labs import labs_bp
    from app.api.symptoms import symptoms_bp
    from app.api.interventions import interventions_bp
    from app.views.main import main_bp

    app.register_blueprint(vitals_bp, url_prefix="/api/vitals")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(medications_bp, url_prefix="/api/medications")
    app.register_blueprint(labs_bp, url_prefix="/api/labs")
    app.register_blueprint(symptoms_bp, url_prefix="/api/symptoms")
    app.register_blueprint(interventions_bp, url_prefix="/api/interventions")
    app.register_blueprint(main_bp)

    # Context processor to inject server time to all templates
    @app.context_processor
    def inject_server_time():
        import time
        return {'server_time_ms': int(time.time() * 1000)}

    return app