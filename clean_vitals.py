from app import create_app, db
from app.models import VitalSign

app = create_app()
with app.app_context():
    num_deleted = db.session.query(VitalSign).delete()
    db.session.commit()
    print(f"Successfully deleted {num_deleted} vitals records.")
