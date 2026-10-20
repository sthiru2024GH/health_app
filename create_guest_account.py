from getpass import getpass

from app import create_app, db
from app.models import User


def main():
    app = create_app()
    with app.app_context():
        name = input("Guest display name [Guest]: ").strip() or "Guest"
        username = input("Guest username: ").strip()
        if not username or len(username) > 50:
            raise SystemExit("Username must contain 1 to 50 characters.")
        if User.query.filter_by(username=username).first():
            raise SystemExit("That username is already in use.")

        password = getpass("Guest password (minimum 8 characters): ")
        confirmation = getpass("Confirm guest password: ")
        if len(password) < 8:
            raise SystemExit("Password must contain at least 8 characters.")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")

        guest = User(username=username, name=name, role="guest")
        guest.set_password(password)
        db.session.add(guest)
        db.session.commit()
        print(f"Read-only guest account created: {username}")


if __name__ == "__main__":
    main()
