"""
Auth business logic, kept separate from the API layer (app/api) so it can be
unit-tested and reused (e.g. by the seed script) without spinning up FastAPI.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import RefreshToken
from app.models.rbac import Role
from app.models.user import User
from app.schemas.auth import UserLogin, UserRegister
from app.security.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)


def register_user(db: Session, data: UserRegister) -> User:
    existing = db.scalar(select(User).where(User.email == data.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    default_role = db.scalar(select(Role).where(Role.name == "USER"))
    if default_role is None:
        # Should never happen if seed script has run, but fail loudly rather
        # than silently creating a role-less (permission-less) account.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default USER role is not configured. Run the seed script first.",
        )

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        preferred_language=data.preferred_language,
        is_active=True,
        is_email_verified=False,
        roles=[default_role],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, data: UserLogin) -> User:
    user = db.scalar(select(User).where(User.email == data.email))
    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    return user


def issue_tokens(db: Session, user: User) -> tuple[str, str]:
    role_names = [r.name for r in user.roles]
    access_token = create_access_token(subject=str(user.id), roles=role_names)

    raw_refresh, refresh_hash = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=refresh_token_expiry(),
            revoked=False,
        )
    )
    db.commit()
    return access_token, raw_refresh


def rotate_refresh_token(db: Session, raw_refresh_token: str) -> tuple[str, str]:
    """Validate an incoming refresh token, revoke it, and issue a fresh pair
    (rotation reduces the blast radius if a refresh token is stolen)."""
    token_hash = hash_refresh_token(raw_refresh_token)
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if stored is None or stored.revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    expires_at = stored.expires_at
    if expires_at.tzinfo is None:
        # SQLite doesn't persist tzinfo on DateTime columns (Postgres does),
        # so normalize to UTC-aware before comparing either way.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    stored.revoked = True
    db.add(stored)
    db.commit()

    return issue_tokens(db, user)


def revoke_refresh_token(db: Session, raw_refresh_token: str) -> None:
    token_hash = hash_refresh_token(raw_refresh_token)
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if stored is not None:
        stored.revoked = True
        db.add(stored)
        db.commit()
