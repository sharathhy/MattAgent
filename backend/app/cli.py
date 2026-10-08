"""Operational commands: ``matt seed-registry`` and ``matt create-owner``."""

import argparse
import getpass
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.services import auth, registry
from app.services.errors import ServiceError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matt")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed-registry", help="Register catalog agents that are not yet in the database")
    owner = sub.add_parser("create-owner", help="Create the owner account (first run only)")
    owner.add_argument("--email", required=True)
    owner.add_argument("--name", default="")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    with get_sessionmaker()() as db:
        try:
            if args.command == "seed-registry":
                result = registry.seed_registry(db)
                print(f"Registry: {result.created} created, {result.existing} already registered")
            else:
                password = getpass.getpass("Owner password (12+ chars): ")
                if len(password) < 12:
                    print("Password must be at least 12 characters", file=sys.stderr)
                    return 1
                user = auth.bootstrap_owner(
                    db, email=args.email, password=password, full_name=args.name
                )
                print(f"Owner created: {user.email}")
        except ServiceError as exc:
            print(exc.message, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
