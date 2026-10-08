from sqlalchemy.orm import Session

from app.core.domain import Role
from app.core.google import GoogleIdentity
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import users as user_repo
from app.services import audit
from app.services.errors import ConflictError, ForbiddenError

#: Stored for accounts that sign in only with Google; never matches any password.
NO_PASSWORD = "!"  # noqa: S105 (a marker, not a credential)


def create_user(
    db: Session,
    *,
    email: str,
    password: str | None,
    full_name: str,
    role: Role,
    created_by: str,
) -> User:
    if user_repo.get_by_email(db, email) is not None:
        raise ConflictError("A user with this email already exists")
    password_hash = hash_password(password) if password is not None else NO_PASSWORD
    user = User(email=email.lower(), full_name=full_name, password_hash=password_hash, role=role)
    db.add(user)
    db.flush()
    audit.record(
        db, actor_type="user" if created_by.isdigit() else "system", actor_id=created_by,
        action="user.created", target_type="user", target_id=str(user.id), details={"role": role},
    )  # fmt: skip
    db.commit()
    return user


def bootstrap_owner(db: Session, *, email: str, password: str, full_name: str) -> User:
    """Create the first (owner) account. Only possible while no users exist."""
    if user_repo.count(db) > 0:
        raise ConflictError("MATT is already initialised; ask the owner for an account")
    return create_user(
        db,
        email=email,
        password=password,
        full_name=full_name,
        role=Role.OWNER,
        created_by="bootstrap",
    )


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = user_repo.get_by_email(db, email)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def sign_in_with_google(db: Session, identity: GoogleIdentity, owner_email: str | None) -> User:
    """Sign in an existing account by its Google-verified email. The only account Google can
    create is the owner, and only for the configured owner email while no users exist."""
    user = user_repo.get_by_email(db, identity.email)
    if user is not None:
        if not user.is_active:
            raise ForbiddenError("This account is disabled")
        return user
    if owner_email and identity.email == owner_email.lower() and user_repo.count(db) == 0:
        return create_user(
            db, email=identity.email, password=None, full_name=identity.name,
            role=Role.OWNER, created_by="google",
        )  # fmt: skip
    raise ForbiddenError("This Google account has not been given access to MATT")
