# src/potato_registry/core/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, OAuth2PasswordBearer

from src.potato_registry.models import User
from src.potato_registry.core.security import decode_access_token, verify_password

security = HTTPBasic(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/users/token", auto_error=False)


async def get_current_pip_user(
    credentials: HTTPBasicCredentials | None = Depends(security, use_cache=False),
) -> User | None:
    """
    Authentifie un utilisateur venant de Pip (Basic Auth).
    Gère le fallback : Mot de passe Local OU Token Pip.
    """
    if not credentials:
        return None  # Pas de header Basic

    # 1. On cherche l'utilisateur par son nom (Rapide car indexé)
    user = await User.get_or_none(username=credentials.username)

    if not user:
        return None

    # 2. Vérification des accès
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Compte désactivé")

    if not user.hashed_password or not verify_password(
        credentials.password, user.hashed_password
    ):
        return None

    await user.fetch_related("roles")

    return user


async def get_current_jwt_user(
    token: str | None = Depends(oauth2_scheme, use_cache=False),
) -> User | None:
    if not token:
        return None  # Pas de header Bearer

    payload = decode_access_token(token)
    if payload is None:
        return None  # Token invalide ou expiré

    username: str = payload.get("sub")

    user = await User.get_or_none(username=username)
    if user is None or not user.is_active:
        return None

    await user.fetch_related("roles")
    return user


async def get_current_jwt_only_user(
    jwt_user: User | None = Depends(get_current_jwt_user, use_cache=False),
) -> User:
    """Exige l'authentification par Bearer Token (JWT) uniquement."""
    if jwt_user:
        return jwt_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise via Bearer Token (JWT).",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_admin_jwt_user(
    jwt_user: User = Depends(get_current_jwt_only_user, use_cache=False),
) -> User:
    """Exige que l'utilisateur JWT soit un administrateur."""
    if not jwt_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès administrateur requis.",
        )
    return jwt_user


async def get_current_hybrid_user(
    basic_user: User | None = Depends(get_current_pip_user, use_cache=False),
    jwt_user: User | None = Depends(get_current_jwt_user, use_cache=False),
) -> User:
    """Exige l'authentification par Basic Auth OU Bearer Token."""
    if basic_user:
        return basic_user
    if jwt_user:
        return jwt_user

    # Si les deux échouent, on lève une 401 avec les deux types d'authentification
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise. Fournir Basic Auth (Pip/uv) ou Bearer Token (JWT).",
        headers={"WWW-Authenticate": 'Basic realm="Potato Registry", Bearer'},
    )
