import re
from datetime import datetime, timezone

from sqlalchemy import inspect, text


def _add_legacy_user_columns(connection, inspector):
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "username" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(50)"))
    if "password_hash" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(256)"))
    if "doctor_id" not in columns:
        connection.execute(text(
            "ALTER TABLE users ADD COLUMN doctor_id INTEGER REFERENCES users (id)"
        ))

    rows = connection.execute(
        text("SELECT id, name, username FROM users ORDER BY id")
    ).mappings().all()
    name_counts = {}
    used_usernames = set()
    for row in rows:
        name = (row["name"] or "").strip()
        if name:
            name_counts[name.casefold()] = name_counts.get(name.casefold(), 0) + 1
        if row["username"]:
            used_usernames.add(row["username"].casefold())

    for row in rows:
        name = (row["name"] or "").strip()
        if (
            not row["username"]
            and name
            and name_counts.get(name.casefold()) == 1
            and name.casefold() not in used_usernames
        ):
            connection.execute(
                text("UPDATE users SET username = :username WHERE id = :user_id"),
                {"username": name, "user_id": row["id"]},
            )
            used_usernames.add(name.casefold())

    duplicates = connection.execute(text(
        "SELECT username FROM users WHERE username IS NOT NULL "
        "GROUP BY username HAVING COUNT(*) > 1"
    )).scalars().all()
    if duplicates:
        raise RuntimeError(
            "Cannot finish legacy user migration: duplicate usernames exist. "
            "Resolve duplicate usernames before restarting the application."
        )

    existing_username_constraint = any(
        constraint.get("column_names") == ["username"]
        for constraint in inspector.get_unique_constraints("users")
    )
    existing_username_index = any(
        index.get("unique") and index.get("column_names") == ["username"]
        for index in inspector.get_indexes("users")
    )
    if not existing_username_constraint and not existing_username_index:
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON users (username)"
        ))


def _split_dosage(dosage):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(.*)", (dosage or "").strip())
    if match:
        return float(match.group(1)), match.group(2).strip() or "dose"
    return 1.0, (dosage or "").strip() or "dose"


def _migrate_postgresql_medication_logs(connection, inspector):
    tables = set(inspector.get_table_names())
    if not {"medication_schedules", "medication_logs"} <= tables:
        return False

    log_columns = {column["name"] for column in inspector.get_columns("medication_logs")}
    if "schedule_id" not in log_columns:
        return False
    if "prescription_item_id" in log_columns:
        raise RuntimeError(
            "Legacy medication_logs contains both schedule_id and "
            "prescription_item_id; refusing to guess how to migrate it."
        )

    schedules = connection.execute(text(
        "SELECT id, patient_id, medication_name, dosage, scheduled_time, instructions "
        "FROM medication_schedules ORDER BY id"
    )).mappings().all()
    logs = connection.execute(text(
        "SELECT id, schedule_id, administered_at, status "
        "FROM medication_logs ORDER BY id"
    )).mappings().all()
    schedule_ids = {schedule["id"] for schedule in schedules}
    orphan_logs = [log["id"] for log in logs if log["schedule_id"] not in schedule_ids]
    if orphan_logs:
        raise RuntimeError(
            "Cannot migrate legacy medication logs with missing schedules: "
            f"{orphan_logs}"
        )

    item_ids = {}
    for schedule in schedules:
        result = connection.execute(text(
            "INSERT INTO prescriptions (patient_id, date_issued, notes) "
            "VALUES (:patient_id, :date_issued, :notes) RETURNING id"
        ), {
            "patient_id": schedule["patient_id"],
            "date_issued": datetime.now(timezone.utc).date(),
            "notes": None,
        })
        prescription_id = result.scalar_one()
        quantity, unit = _split_dosage(schedule["dosage"])
        item_id = connection.execute(text(
            "INSERT INTO prescription_items "
            "(prescription_id, drug_name, quantity, unit, time_of_day, dependent_event) "
            "VALUES (:prescription_id, :drug_name, :quantity, :unit, "
            ":time_of_day, :dependent_event) RETURNING id"
        ), {
            "prescription_id": prescription_id,
            "drug_name": schedule["medication_name"],
            "quantity": quantity,
            "unit": unit,
            "time_of_day": schedule["scheduled_time"],
            "dependent_event": schedule["instructions"],
        }).scalar_one()
        item_ids[schedule["id"]] = item_id

    connection.execute(text(
        "ALTER TABLE medication_logs ADD COLUMN prescription_item_id INTEGER"
    ))
    for log in logs:
        connection.execute(text(
            "UPDATE medication_logs SET prescription_item_id = :item_id WHERE id = :log_id"
        ), {"item_id": item_ids[log["schedule_id"]], "log_id": log["id"]})

    for foreign_key in inspector.get_foreign_keys("medication_logs"):
        if "schedule_id" in foreign_key.get("constrained_columns", []):
            name = foreign_key.get("name")
            if not name:
                raise RuntimeError(
                    "Cannot migrate legacy medication_logs: its schedule foreign key "
                    "has no name."
                )
            quoted_name = connection.dialect.identifier_preparer.quote(name)
            connection.execute(text(
                f"ALTER TABLE medication_logs DROP CONSTRAINT {quoted_name}"
            ))

    connection.execute(text(
        "ALTER TABLE medication_logs DROP COLUMN schedule_id"
    ))
    connection.execute(text(
        "ALTER TABLE medication_logs ALTER COLUMN prescription_item_id SET NOT NULL"
    ))
    connection.execute(text(
        "ALTER TABLE medication_logs ADD CONSTRAINT "
        "fk_medication_logs_prescription_item_id "
        "FOREIGN KEY (prescription_item_id) REFERENCES prescription_items (id)"
    ))
    return True


def _migrate_sqlite_medication_logs(engine):
    connection = engine.raw_connection()
    cursor = connection.cursor()
    try:
        tables = {
            row[0] for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not {"medication_schedules", "medication_logs"} <= tables:
            return False

        log_columns = {
            row[1] for row in cursor.execute("PRAGMA table_info(medication_logs)")
        }
        if "schedule_id" not in log_columns:
            return False
        if "prescription_item_id" in log_columns:
            raise RuntimeError(
                "Legacy medication_logs contains both schedule_id and "
                "prescription_item_id; refusing to guess how to migrate it."
            )

        cursor.execute("PRAGMA foreign_keys = OFF")
        cursor.execute("BEGIN IMMEDIATE")
        schedules = cursor.execute(
            "SELECT id, patient_id, medication_name, dosage, scheduled_time, instructions "
            "FROM medication_schedules ORDER BY id"
        ).fetchall()
        logs = cursor.execute(
            "SELECT id, schedule_id, administered_at, status "
            "FROM medication_logs ORDER BY id"
        ).fetchall()
        schedule_ids = {schedule[0] for schedule in schedules}
        orphan_logs = [log[0] for log in logs if log[1] not in schedule_ids]
        if orphan_logs:
            raise RuntimeError(
                "Cannot migrate legacy medication logs with missing schedules: "
                f"{orphan_logs}"
            )

        item_ids = {}
        for schedule_id, patient_id, drug_name, dosage, scheduled_time, instructions in schedules:
            cursor.execute(
                "INSERT INTO prescriptions (patient_id, date_issued, notes) VALUES (?, ?, ?)",
                (patient_id, datetime.now(timezone.utc).date().isoformat(), None),
            )
            prescription_id = cursor.lastrowid
            quantity, unit = _split_dosage(dosage)
            cursor.execute(
                "INSERT INTO prescription_items "
                "(prescription_id, drug_name, quantity, unit, time_of_day, dependent_event) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (prescription_id, drug_name, quantity, unit, scheduled_time, instructions),
            )
            item_ids[schedule_id] = cursor.lastrowid

        cursor.execute(
            "CREATE TABLE medication_logs_new ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "prescription_item_id INTEGER NOT NULL, "
            "administered_at DATETIME, status VARCHAR(20), "
            "FOREIGN KEY (prescription_item_id) REFERENCES prescription_items (id))"
        )
        cursor.executemany(
            "INSERT INTO medication_logs_new "
            "(id, prescription_item_id, administered_at, status) VALUES (?, ?, ?, ?)",
            [
                (log_id, item_ids[schedule_id], administered_at, status)
                for log_id, schedule_id, administered_at, status in logs
            ],
        )
        cursor.execute("DROP TABLE medication_logs")
        cursor.execute("ALTER TABLE medication_logs_new RENAME TO medication_logs")
        violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                f"Legacy medication migration failed foreign key checks: {violations}"
            )
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()
            connection.close()


def migrate_legacy_schema(engine, logger):
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text(
                "SELECT pg_advisory_xact_lock(hashtext('health_app_schema_migration'))"
            ))
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "users" in tables:
            _add_legacy_user_columns(connection, inspector)
        if "prescriptions" in tables:
            columns = {
                column["name"] for column in inspector.get_columns("prescriptions")
            }
            if "closed_at" not in columns:
                column_type = (
                    "TIMESTAMP WITH TIME ZONE"
                    if engine.dialect.name == "postgresql"
                    else "DATETIME"
                )
                connection.execute(text(
                    f"ALTER TABLE prescriptions ADD COLUMN closed_at {column_type}"
                ))
        if "interventions" in tables:
            columns = {
                column["name"] for column in inspector.get_columns("interventions")
            }
            if "diagnosis" not in columns:
                connection.execute(text(
                    "ALTER TABLE interventions ADD COLUMN diagnosis VARCHAR(200)"
                ))
            if "status" not in columns:
                connection.execute(text(
                    "ALTER TABLE interventions ADD COLUMN status VARCHAR(20) DEFAULT 'active'"
                ))
        if "vital_signs" in tables:
            columns = {
                column["name"] for column in inspector.get_columns("vital_signs")
            }
            if "weight_kg" not in columns:
                connection.execute(text(
                    "ALTER TABLE vital_signs ADD COLUMN weight_kg FLOAT"
                ))

    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text(
                "SELECT pg_advisory_xact_lock(hashtext('health_app_schema_migration'))"
            ))
            inspector = inspect(connection)
            if _migrate_postgresql_medication_logs(connection, inspector):
                logger.info("Migrated legacy medication schedules and logs to prescriptions.")
    elif engine.dialect.name == "sqlite":
        if _migrate_sqlite_medication_logs(engine):
            logger.info("Migrated legacy medication schedules and logs to prescriptions.")
