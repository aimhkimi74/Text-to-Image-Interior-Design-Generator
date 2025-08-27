import os
import sys
from getpass import getpass
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Add the current directory to the path so we can import the app
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Import the app and db
from app import create_app, db
from app.models import User


# ---------------------------
# Password validation helper
# ---------------------------
def validate_password_strength(password: str) -> (bool, str):
    """Check password strength rules."""
    if len(password) < 12:
        return False, "Password must be at least 12 characters."
    if not any(c.islower() for c in password):
        return False, "Password must include a lowercase letter."
    if not any(c.isupper() for c in password):
        return False, "Password must include an uppercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must include a digit."
    if not any(c in "!@#$%^&*()-_=+[]{};:,<.>/?\\|" for c in password):
        return False, "Password must include a special character."
    return True, ""


# ---------------------------
# Create or update admin user
# ---------------------------
def create_admin_user(username, email, password, update_if_exists=False):
    """Create a new admin user or update an existing user to have admin privileges."""
    app = create_app()

    with app.app_context():
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing_user:
            if update_if_exists:
                existing_user.is_admin = True
                if password:  # update password if provided
                    existing_user.password = generate_password_hash(password)
                db.session.commit()
                print(f"✅ User '{existing_user.username}' updated with admin privileges.")
                return True
            else:
                print(
                    f"⚠️ User with username '{username}' or email already exists.\n"
                    f"Use --update to grant admin privileges instead."
                )
                return False
        else:
            new_user = User(
                username=username,
                email=email,
                password=generate_password_hash(password),
                is_verified=True,  # Auto-verify admin users
                is_admin=True,
            )
            db.session.add(new_user)
            db.session.commit()
            print(f"✅ Admin user '{username}' created successfully!")
            return True


# ---------------------------
# CLI Entrypoint
# ---------------------------
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Create an admin user for the application.")
    parser.add_argument("--username", "-u", help="Admin username")
    parser.add_argument("--email", "-e", help="Admin email")
    parser.add_argument("--password", "-p", help="Admin password (not recommended, use interactive prompt instead)")
    parser.add_argument("--update", action="store_true", help="Update existing user with admin privileges")

    args = parser.parse_args()

    username = args.username or input("Enter admin username: ").strip()
    email = args.email or input("Enter admin email: ").strip()
    password = args.password

    if not password:
        password = getpass("Enter admin password: ")
        confirm = getpass("Confirm admin password: ")
        if password != confirm:
            print("❌ Error: Passwords do not match.")
            return False

    # Validate password strength
    valid, msg = validate_password_strength(password)
    if not valid:
        print(f"❌ Error: {msg}")
        return False

    return create_admin_user(username, email, password, args.update)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
