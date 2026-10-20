from getpass import getpass

from app import create_app, db
from app.models import User


def main():
    app = create_app()
    with app.app_context():
        accounts = User.query.filter(
            (User.password_hash.is_(None)) | (User.password_hash == "")
        ).order_by(User.id).all()
        if not accounts:
            print("No legacy accounts need credential setup.")
            return

        print("Legacy accounts without login credentials:")
        for account in accounts:
            print(f"  ID {account.id}: {account.name} ({account.role})")

        try:
            user_id = int(input("Account ID to activate: ").strip())
        except ValueError as error:
            raise SystemExit("Account ID must be a number.") from error

        user = db.session.get(User, user_id)
        if not user or user.password_hash:
            raise SystemExit("That account does not need legacy credential setup.")

        username = input(
            f"Username [{user.username or user.name}]: "
        ).strip() or user.username or user.name
        if not username or len(username) > 50:
            raise SystemExit("Username must contain 1 to 50 characters.")
        existing_user = User.query.filter(
            db.func.lower(User.username) == username.casefold(),
            User.id != user.id,
        ).first()
        if existing_user:
            raise SystemExit("That username is already in use.")

        password = getpass("New password (minimum 8 characters): ")
        confirmation = getpass("Confirm new password: ")
        if len(password) < 8:
            raise SystemExit("Password must contain at least 8 characters.")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")

        user.username = username
        user.set_password(password)
        db.session.commit()
        print(f"Login credentials set for legacy account ID {user.id}.")


if __name__ == "__main__":
    main()
