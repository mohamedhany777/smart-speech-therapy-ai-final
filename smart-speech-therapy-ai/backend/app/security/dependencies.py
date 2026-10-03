"""
FastAPI dependencies that enforce authentication and authorization at the
API layer. Per spec section 3/4: authorization is ALWAYS checked on the
backend — the frontend hiding a button is not a security control.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.security.tokens import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
# Same scheme, but does not reject anonymous requests — for endpoints that are
# public by default but unlock extra data for privileged callers.
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise CREDENTIALS_EXCEPTION

    user_id = payload.get("sub")
    if user_id is None:
        raise CREDENTIALS_EXCEPTION

    user = db.get(User, user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    return user


def get_optional_user(token: str | None = Depends(oauth2_scheme_optional), db: Session = Depends(get_db)) -> User | None:
    """Return the authenticated user, or None for anonymous/invalid tokens."""
    if not token:
        return None
    try:
        return get_current_user(token, db)
    except HTTPException:
        return None


def assert_can_view_inactive(user: User | None, permission_code: str) -> None:
    """Guard for `include_inactive=true` listings: hidden (deactivated) content
    is only visible to callers who can manage it."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view inactive items",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.has_permission(permission_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission_code}",
        )


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


def require_roles(*allowed_roles: str):
    """Dependency factory: require the user to hold at least one of the given roles.

    Usage: `Depends(require_roles("ADMIN"))` or `Depends(require_roles("ADMIN", "SPECIALIST"))`
    """

    def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        user_role_names = {r.name for r in current_user.roles}
        if not user_role_names.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed_roles)}",
            )
        return current_user

    return dependency


def require_permission(permission_code: str):
    """Dependency factory: require a specific fine-grained permission,
    e.g. Depends(require_permission("manage_knowledge_base"))."""

    def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if not current_user.has_permission(permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission_code}",
            )
        return current_user

    return dependency
