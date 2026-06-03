from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from clusterspider.auth.jwt import verify_token
from clusterspider.auth.models import User, UserRepository
from clusterspider.graph.driver import get_driver
from clusterspider.graph.repository import GraphRepository

security = HTTPBearer()

_user_repo: UserRepository | None = None


def get_user_repo() -> UserRepository:
    global _user_repo
    if _user_repo is None:
        _user_repo = UserRepository()
    return _user_repo


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    payload = verify_token(credentials.credentials, expected_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    repo = get_user_repo()
    user = repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


async def get_graph_repo() -> GraphRepository:
    driver = await get_driver()
    return GraphRepository(driver)
