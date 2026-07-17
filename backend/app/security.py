import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import Role, User

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        # Deliberately generic: distinguishing "expired" from "malformed/tampered" to the
        # client isn't useful and the 401 branch below is what session-expiry handling keys off.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    user = db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
    if not user.is_active:
        # Covers the "admin deactivates provider mid-draft" non-happy-path: every subsequent
        # authenticated request from that provider fails closed here, not just at login.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account has been deactivated")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_provider(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.provider:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Provider access required")
    return user


def require_provider_or_admin(user: User = Depends(get_current_user)) -> User:
    # Lets an admin edit/generate/save a note on any provider's encounter (see
    # _get_owned_encounter's admin bypass in routers/encounters.py), not just view it.
    if user.role not in (Role.provider, Role.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Provider or admin access required")
    return user
