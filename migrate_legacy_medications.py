import os
import re
import sqlite3
from datetime import date

from app import create_app, db


def _split_dosage(dosage):
    dosage = (dosage or "").strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(.*)", dosage)
    if match:
        return float(match.group(1)), match.group(2).strip() or "dose"
    return 1.0, dosage or "dose"


def migrate_legacy_medications(connection):
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if "medication_logs" not in tables:
        raise RuntimeError("The medication_logs table does not exist.")

    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(medication_logs)")
    }
    if "prescription_item_id" in columns and "schedule_id" not in columns:
        return 0, 0
    if "schedule_id" not in columns or "prescription_item_id" in columns:
        raise RuntimeError("The medication_logs schema is not a supported legacy schema.")
    if not {"medication_schedules", "prescriptions", "prescription_items"} <= tables:
        raise RuntimeError("Required medication tables are missing.")

    schedules = connection.execute(
        """
        SELECT id, patient_id, medication_name, dosage, scheduled_time, instructions
        FROM medication_schedules
        ORDER BY id
        """
    ).fetchall()
    logs = connection.execute(
        "SELECT id, schedule_id, administered_at, status FROM medication_logs ORDER BY id"
    ).fetchall()
    schedule_ids = {schedule[0] for schedule in schedules}
    orphan_log_ids = [log[0] for log in logs if log[1] not in schedule_ids]
    if orphan_log_ids:
        raise RuntimeError(
            f"Cannot migrate medication logs with missing schedules: {orphan_log_ids}"
        )

    if "medication_logs_new" in tables:
        raise RuntimeError("A previous medication migration left medication_logs_new behind.")

    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        item_ids = {}
        for schedule_id, patient_id, name, dosage, scheduled_time, instructions in schedules:
            result = connection.execute(
                """
                INSERT INTO prescriptions (patient_id, date_issued)
                VALUES (?, ?)
                """,
                (patient_id, date.today().isoformat()),
            )
            prescription_id = result.lastrowid
            quantity, unit = _split_dosage(dosage)
            result = connection.execute(
                """
                INSERT INTO prescription_items (
                    prescription_id, drug_name, quantity, unit, time_of_day, dependent_event
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    prescription_id,
                    name,
                    quantity,
                    unit,
                    scheduled_time,
                    instructions,
                ),
            )
            item_ids[schedule_id] = result.lastrowid

        connection.execute(
            """
            CREATE TABLE medication_logs_new (
                id INTEGER NOT NULL PRIMARY KEY,
                prescription_item_id INTEGER NOT NULL,
                administered_at DATETIME,
                status VARCHAR(20),
                FOREIGN KEY (prescription_item_id) REFERENCES prescription_items (id)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO medication_logs_new (
                id, prescription_item_id, administered_at, status
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (log_id, item_ids[schedule_id], administered_at, status)
                for log_id, schedule_id, administered_at, status in logs
            ],
        )
        connection.execute("DROP TABLE medication_logs")
        connection.execute(
            "ALTER TABLE medication_logs_new RENAME TO medication_logs"
        )

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                f"Foreign key checks failed after migration: {violations}"
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")

    return len(schedules), len(logs)


def main():
    app = create_app()
    with app.app_context():
        if db.engine.dialect.name != "sqlite":
            raise RuntimeError(
                "This migration currently supports SQLite databases only."
            )
        database_path = db.engine.url.database
        if not database_path or database_path == ":memory:":
            raise RuntimeError("A file-backed SQLite database is required.")
        if not os.path.isabs(database_path):
            database_path = os.path.join(app.instance_path, database_path)

    with sqlite3.connect(database_path) as connection:
        schedules_migrated, logs_migrated = migrate_legacy_medications(connection)

    if schedules_migrated == 0 and logs_migrated == 0:
        print("Medication database is already on the current schema.")
    else:
        print(
            f"Migrated {schedules_migrated} medication schedules and "
            f"{logs_migrated} medication logs."
        )
        print("Legacy medication_schedules rows were retained.")


if __name__ == "__main__":
    main()
