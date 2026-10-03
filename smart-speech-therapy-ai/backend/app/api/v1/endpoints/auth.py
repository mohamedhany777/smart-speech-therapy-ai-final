from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import RefreshRequest, TokenResponse, UserLogin, UserOut, UserRegister
from app.security.dependencies import get_current_active_user
from app.security.rate_limit import rate_limit_login
from app.services import audit_service, auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserRegister, db: Session = Depends(get_db)):
    user = auth_service.register_user(db, data)
    audit_service.log_event(db, action="user.register", user_id=str(user.id))
    return UserOut.from_model(user)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit_login)])
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = auth_service.authenticate_user(db, data)
    access_token, refresh_token = auth_service.issue_tokens(db, user)
    audit_service.log_event(db, action="user.login", user_id=str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    access_token, refresh_token = auth_service.rotate_refresh_token(db, data.refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=204)
def logout(data: RefreshRequest, db: Session = Depends(get_db)):
    auth_service.revoke_refresh_token(db, data.refresh_token)
    return None


@router.get("/me", response_model=UserOut)
def me(current_user=Depends(get_current_active_user)):
    return UserOut.from_model(current_user)
