# src/mon_registre/routes/users.py
from fastapi import APIRouter, HTTPException, status
from typing import List
from passlib.context import CryptContext
from tortoise.exceptions import IntegrityError

from src.potato_registry.models import User
from src.potato_registry.schemas import UserCreate, UserResponse, UserUpdate

# Configuration du hachage
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

router = APIRouter(prefix="/api/users", tags=["Users Management"])


# --- CREATE ---
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate):
    # Hachage du mot de passe
    hashed_pwd = pwd_context.hash(user_in.password)

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
        user.hashed_password = pwd_context.hash(user_in.password)

    await user.save()
    return user


# --- DELETE ---
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int):
    deleted_count = await User.filter(id=user_id).delete()
    if not deleted_count:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
