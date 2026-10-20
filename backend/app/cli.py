"""
Controlled CLI utility for Rumi Dental Care administration.
Usage (from backend/ or project root):
  python -m app.cli create-admin --email admin@rumidentalcare.com --name "Dr. Aisha Salman"
  python -m app.cli seed
"""
import argparse
import getpass
import sys
from app.core.security import validate_password_strength
from app.db.session import SessionLocal
from app.services.seed_service import provision_admin_account, seed_initial_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Rumi Dental Care — Administrative CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    admin_parser = subparsers.add_parser("create-admin", help="Provision or update an Administrator account securely")
    admin_parser.add_argument("--email", required=True, help="Administrator email address")
    admin_parser.add_argument("--name", required=True, help="Administrator full name")
    admin_parser.add_argument("--phone", default="+92 310 2468080", help="Administrator phone number")
    admin_parser.add_argument("--password", default=None, help="Administrator password (omit to prompt securely)")

    seed_parser = subparsers.add_parser("seed", help="Seed clinic settings, services, and genuine testimonials")
    seed_parser.add_argument("--no-demo", action="store_true", help="Skip synthetic demo patient records")

    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.command == "create-admin":
            pwd = args.password
            if not pwd:
                pwd = getpass.getpass("Enter strong password for Administrator: ")
                pwd_confirm = getpass.getpass("Confirm password: ")
                if pwd != pwd_confirm:
                    print("ERROR: Passwords do not match.", file=sys.stderr)
                    return 1
            err = validate_password_strength(pwd)
            if err:
                print(f"ERROR: {err}", file=sys.stderr)
                return 1
            user = provision_admin_account(
                db=db,
                email=args.email,
                full_name=args.name,
                password=pwd,
                phone=args.phone,
            )
            print(f"SUCCESS: Administrator '{user.full_name}' <{user.email}> provisioned (User ID: {user.id}).")
            return 0

        if args.command == "seed":
            seed_initial_data(db=db, include_demo_records=not args.no_demo)
            print("SUCCESS: Rumi Dental Care database seeded.")
            return 0
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
