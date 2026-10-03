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

    # Register blueprints
    from app.api.vitals import vitals_bp
    app.register_blueprint(vitals_bp, url_prefix="/api/vitals")

    return app