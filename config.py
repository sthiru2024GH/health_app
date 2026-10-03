import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

# Ensure the instance directory exists before SQLite tries to write to it
os.makedirs(INSTANCE_DIR, exist_ok=True)


import os

class Config:
    # Get DATABASE_URL from environment
    db_url = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    
    # Fix Render's legacy 'postgres://' prefix & specify psycopg2 driver
    if db_url and db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    elif db_url and db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+psycopg2://', 1)

    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False


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