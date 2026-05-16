import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "coachlenz-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

security = HTTPBearer()


def create_token(coach_id: str, email: str, role: str = "assistant") -> str:
    """Create a signed JWT token for a coach."""
    payload = {
        "sub": coach_id,
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Returns the coach payload dict."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_coach(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """FastAPI dependency that extracts and validates the current coach from JWT."""
    token = credentials.credentials
    payload = decode_token(token)

    coach_id = payload.get("sub")
    email = payload.get("email")

    if not coach_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing required fields",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": coach_id,
        "email": email,
        "role": payload.get("role", "assistant"),
    }


def require_head_coach(coach: dict = Depends(get_current_coach)) -> dict:
    """Dependency that requires head coach role."""
    if coach["role"] not in ("head", "coordinator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Head coach or coordinator role required",
        )
    return coach
