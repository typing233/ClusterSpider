from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from clusterspider.auth.models import User
from clusterspider.auth.encryption import encrypt_api_key
from clusterspider.api.dependencies import get_current_user, get_user_repo

router = APIRouter()


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    created_at: str
    last_login: str | None


class ApiKeyCreateRequest(BaseModel):
    service_name: str
    api_key: str


class ApiKeyResponse(BaseModel):
    id: str
    service_name: str
    created_at: str


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.post("/me/api-keys", response_model=ApiKeyResponse)
async def create_api_key(data: ApiKeyCreateRequest, user: User = Depends(get_current_user)):
    repo = get_user_repo()
    encrypted = encrypt_api_key(data.api_key)
    key_id = repo.store_api_key(user.id, data.service_name, encrypted)
    return ApiKeyResponse(id=key_id, service_name=data.service_name, created_at="")


@router.get("/me/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(user: User = Depends(get_current_user)):
    repo = get_user_repo()
    keys = repo.get_api_keys(user.id)
    return [ApiKeyResponse(**k) for k in keys]


@router.delete("/me/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: User = Depends(get_current_user)):
    repo = get_user_repo()
    if not repo.delete_api_key(key_id, user.id):
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "deleted"}
