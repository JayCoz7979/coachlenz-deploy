import os
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from lib.supabase_client import get_table
from lib.auth import create_token
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_KEY = os.getenv("COACHLENZ_ADMIN_KEY", "")


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "assistant"
    admin_key: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    coach_id: str
    name: str
    email: str
    role: str


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    """Authenticate a coach and return a JWT."""
    result = get_table("coaches").select("*").eq("email", body.email).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    coach = result.data[0]

    if not pwd_context.verify(body.password, coach["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_token(
        coach_id=coach["id"],
        email=coach["email"],
        role=coach["role"],
    )

    return AuthResponse(
        access_token=token,
        coach_id=coach["id"],
        name=coach["name"],
        email=coach["email"],
        role=coach["role"],
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """Register a new coach. Requires admin key."""
    if not ADMIN_KEY or body.admin_key != ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key",
        )

    # Check if email already exists
    existing = get_table("coaches").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A coach with this email already exists",
        )

    if body.role not in ("head", "assistant", "coordinator"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of: head, assistant, coordinator",
        )

    password_hash = pwd_context.hash(body.password)

    new_coach = {
        "name": body.name,
        "email": body.email,
        "password_hash": password_hash,
        "role": body.role,
        "team_ids": [],
    }

    result = get_table("coaches").insert(new_coach).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create coach",
        )

    coach = result.data[0]
    token = create_token(
        coach_id=coach["id"],
        email=coach["email"],
        role=coach["role"],
    )

    return AuthResponse(
        access_token=token,
        coach_id=coach["id"],
        name=coach["name"],
        email=coach["email"],
        role=coach["role"],
    )
