import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

# Ensure the instance directory exists before SQLite tries to write to it
os.makedirs(INSTANCE_DIR, exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(INSTANCE_DIR, 'health_app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Fix Render's legacy 'postgres://' prefix for SQLAlchemy compatibility
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith(
        "postgres://"
    ):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # Fall back to base Config's URI logic if DATABASE_URL isn't explicitly set
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", Config.SQLALCHEMY_DATABASE_URI
    )


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}