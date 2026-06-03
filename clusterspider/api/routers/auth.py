from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from clusterspider.auth.jwt import create_access_token, create_refresh_token, verify_token
from clusterspider.auth.models import UserCreate, UserRepository
from clusterspider.api.dependencies import get_user_repo

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest):
    repo = get_user_repo()

    if repo.get_by_username(data.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    if repo.get_by_email(data.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = repo.create_user(UserCreate(
        username=data.username,
        email=data.email,
        password=data.password,
    ))

    access_token = create_access_token({"sub": user.id, "username": user.username})
    refresh_token = create_refresh_token({"sub": user.id})

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest):
    repo = get_user_repo()
    user = repo.authenticate(data.username, data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token = create_access_token({"sub": user.id, "username": user.username})
    refresh_token = create_refresh_token({"sub": user.id})

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest):
    payload = verify_token(data.refresh_token, expected_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    repo = get_user_repo()
    user = repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token({"sub": user.id, "username": user.username})
    refresh_token = create_refresh_token({"sub": user.id})

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
