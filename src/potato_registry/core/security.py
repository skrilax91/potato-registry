# src/potato_registry/core/security.py
from datetime import UTC, datetime, timedelta
import secrets
from passlib.context import CryptContext

from src.potato_registry.models import User
from src.potato_registry.core.config import settings
from jose import JWTError, jwt

# Configuration unique pour le hachage (Argon2)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe ou un token haché."""
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hache un mot de passe."""
    return pwd_context.hash(password)


def get_user_labels(user: User) -> set[str]:
    """Extrait tous les labels uniques depuis les rôles de l'utilisateur."""
    labels = set()
    for role in user.roles:
        labels.update(role.allowed_labels)
    return labels


def generate_secure_token(length: int = 40) -> str:
    """
    Génère une chaîne aléatoire et sécurisée de longueur spécifiée.
    """
    return secrets.token_urlsafe(length)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Crée un JWT pour l'authentification Bearer."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.app.jwt_access_token_expire_minutes
        )

    to_encode.update({"exp": expire, "sub": data["username"]})

    encoded_jwt = jwt.encode(
        to_encode, settings.app.secret_key, algorithm=settings.app.jwt_algorithm
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """Décode un JWT. Retourne le payload ou None en cas d'erreur (expiré, invalide)."""
    try:
        payload = jwt.decode(
            token, settings.app.secret_key, algorithms=[settings.app.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None
