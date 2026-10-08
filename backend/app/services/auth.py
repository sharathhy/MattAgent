from sqlalchemy.orm import Session

from app.core.domain import Role
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import users as user_repo
from app.services import audit
from app.services.errors import ConflictError


def create_user(
    db: Session, *, email: str, password: str, full_name: str, role: Role, created_by: str
) -> User:
    if user_repo.get_by_email(db, email) is not None:
        raise ConflictError("A user with this email already exists")
    user = User(
        email=email.lower(), full_name=full_name, password_hash=hash_password(password), role=role
    )
    db.add(user)
    db.flush()
    audit.record(
        db, actor_type="system" if created_by == "bootstrap" else "user", actor_id=created_by,
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
