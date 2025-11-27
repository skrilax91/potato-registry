# src/mon_registre/routes/users.py
from fastapi import APIRouter, HTTPException, status
from typing import List
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordRequestForm
from tortoise.exceptions import IntegrityError

from src.potato_registry.core.config import settings
from src.potato_registry.core.deps import (
    get_current_jwt_only_user,
)
from src.potato_registry.models import User
from src.potato_registry.schemas import (
    TokenGenerateResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from src.potato_registry.core.security import (
    create_access_token,
    generate_secure_token,
    get_password_hash,
    verify_password,
)

router = APIRouter(prefix="/api/users", tags=["Users Management"])


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Échange nom d'utilisateur et mot de passe contre un JWT."""
    user = await User.get_or_none(username=form_data.username)

    if not settings.auth.local_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="L'authentification locale est désactivée.",
        )

    # Vérification : utilisateur existe et mot de passe correspond (nécessite le hashed_password)
    if (
        not user
        or not user.hashed_password
        or not verify_password(form_data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Création du token
    access_token = create_access_token(data={"username": user.username})
    return {"access_token": access_token}


# --- CREATE ---
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate):
    # Hachage du mot de passe
    hashed_pwd = get_password_hash(user_in.password)
    try:
        user_obj = await User.create(
            username=user_in.username,
            hashed_password=hashed_pwd,
            email=user_in.email,
            is_service_account=user_in.is_service_account,
        )
    except IntegrityError:
        # Gère le cas où l'username existe déjà
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cet utilisateur existe déjà.",
        )
    return user_obj


# --- LIST ---
@router.get("/", response_model=List[UserResponse])
async def list_users():
    return await User.all()


# --- GET ONE ---
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return user


# --- UPDATE ---
@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_in: UserUpdate):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    # On ne met à jour que les champs fournis
    if user_in.email is not None:
        user.email = user_in.email
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    if user_in.password is not None:
        user.hashed_password = get_password_hash(user_in.password)
    if user_in.is_superuser is not None:
        user.is_superuser = user_in.is_superuser

    await user.save()
    return user


# --- DELETE ---
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int):
    deleted_count = await User.filter(id=user_id).delete()
    if not deleted_count:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")


@router.post(
    "/{user_id}/generate-token", response_model=TokenGenerateResponse, status_code=201
)
async def generate_token(
    user_id: int,
    current_user: User = Depends(get_current_jwt_only_user),
):
    if current_user.id != user_id:
        # Cas 2 : Génération pour un autre (vérification des droits admin)
        if current_user.is_superuser:
            # L'utilisateur a le rôle admin, on cherche la cible
            target_user = await User.get_or_none(id=user_id)
            if not target_user:
                raise HTTPException(
                    status_code=404,
                    detail=f"Utilisateur cible '{user_id}' introuvable.",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé. Vous ne pouvez générer des tokens que pour votre propre compte.",
            )
    else:
        # Cas 1 : Génération pour soi-même
        target_user = current_user

    if not target_user.is_service_account and not target_user.is_sso_managed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Les tokens ne peuvent être générés que pour les comptes de service ou gérés par SSO.",
        )

    # 1. Génération du Token brut
    new_token = generate_secure_token()

    # 2. Hachage et enregistrement
    hashed_token = get_password_hash(new_token)
    target_user.hashed_password = hashed_token
    await target_user.save()

    # 3. Message de confirmation
    if target_user.id == current_user.id:
        msg = "Nouveau token généré et enregistré sur votre compte."
    else:
        msg = f"Nouveau token généré et enregistré pour l'utilisateur '{target_user.username}'."

    msg += " **Attention: Copiez-le maintenant, il ne sera plus affiché.**."

    return {"token": new_token, "message": msg}
