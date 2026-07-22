"""Authentication via Neon JWKS validation.

The frontend handles login/registration via Neon Auth.
The backend only validates JWTs using Neon's JWKS URL.
"""

import structlog
from typing import Annotated, Optional
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models.database import User
from app.models.schemas import UserResponse, UserRole, ErrorResponse

logger = structlog.get_logger(__name__)

router = APIRouter()
security = HTTPBearer()

_jwk_client: Optional[PyJWKClient] = None


def get_jwk_client() -> PyJWKClient:
    """Get or create the JWKS client."""
    global _jwk_client
    
    if _jwk_client is None:
        settings = get_settings()
        if not settings.neon_jwks_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="NEON_JWKS_URL not configured",
            )
        _jwk_client = PyJWKClient(settings.neon_jwks_url)
    
    return _jwk_client


async def validate_jwt(token: str) -> dict:
    """Validate JWT using Neon JWKS."""
    settings = get_settings()
    
    try:
        jwk_client = get_jwk_client()
        signing_key = jwk_client.get_signing_key_from_jwt(token)

        unverified_header = jwt.get_unverified_header(token)
        algorithm = unverified_header.get("alg", "EdDSA")
        
        logger.debug(f"Validating token with algorithm: {algorithm}")

        decode_options = {}
        audience = None
        issuer = None
        
        if settings.neon_jwt_audience:
            audience = settings.neon_jwt_audience
        else:
            decode_options["verify_aud"] = False
            
        if settings.neon_jwt_issuer:
            issuer = settings.neon_jwt_issuer
        else:
            decode_options["verify_iss"] = False
        
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            audience=audience,
            issuer=issuer,
            options=decode_options,
        )
        return payload
        
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as e:
        logger.error(f"JWT validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected JWT error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get the current authenticated user from Neon JWT token."""
    payload = await validate_jwt(credentials.credentials)

    user_id = payload.get("sub")
    email = payload.get("email", "")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user and email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if user:
            user.id = UUID(user_id) if isinstance(user_id, str) else user_id
            await db.flush()
            logger.info(f"Updated user ID for: {user.email}")

    if not user:
        neon_role = payload.get("role", "")
        valid_roles = {"rep", "manager", "admin"}
        db_role = neon_role if neon_role in valid_roles else "rep"
        
        user = User(
            id=UUID(user_id) if isinstance(user_id, str) else user_id,
            email=email,
            name=payload.get("name", email or "User"),
            role=db_role,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info(f"Created new user from Neon auth: {user.email}")

    return user


async def require_manager(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require the current user to be a manager or admin."""
    if current_user.role not in (UserRole.MANAGER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="マネージャーまたは管理者の権限が必要です",
        )
    return current_user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require the current user to be an admin."""
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者の権限が必要です",
        )
    return current_user


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorResponse}},
)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Get current authenticated user information."""
    return UserResponse.model_validate(current_user)