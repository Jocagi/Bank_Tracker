#!/usr/bin/env python3
"""Create initial admin user for Bank Tracker.

Usage:
  python scripts/create_admin.py --username admin --password admin

If the user exists, the script will exit with a message.
"""
import argparse
import sys
from getpass import getpass

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User


def main():
    parser = argparse.ArgumentParser(description='Create admin user')
    parser.add_argument('--username', '-u', help='Username for admin (default: admin)', default='admin')
    parser.add_argument('--password', '-p', help='Password for admin (if omitted, prompt)')
    args = parser.parse_args()

    username = args.username.strip()
    password = args.password
    if not password:
        password = getpass('Password for admin: ')
        password2 = getpass('Confirm password: ')
        if password != password2:
            print('Passwords do not match', file=sys.stderr)
            sys.exit(2)

    app = create_app()
    with app.app_context():
        # Ensure tables exist (if migrations not run)
        try:
            db.create_all()
        except Exception as e:
            print('Warning: could not create tables automatically:', e)

        existing = User.query.filter_by(username=username).first()
        if existing:
            print(f"User '{username}' already exists with id={existing.id}")
            return

        user = User(username=username, password_hash=generate_password_hash(password), role='admin')
        db.session.add(user)
        db.session.commit()
        print(f"Admin user '{username}' created with id={user.id}")


if __name__ == '__main__':
    main()
