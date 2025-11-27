# src/mon_registre/schemas.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


# Ce qu'on renvoie au client (JAMAIS de password ici)
class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    is_active: bool
    is_superuser: bool
    is_service_account: bool
    is_sso_managed: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True  # Permet de lire depuis l'objet Tortoise


# Ce qu'on attend pour la création
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    email: Optional[EmailStr] = None
    is_service_account: bool = False
    is_superuser: bool = False


# Ce qu'on attend pour la mise à jour (tout est optionnel)
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class UserRoleAssign(BaseModel):
    role_ids: list[int]


class RoleCreate(BaseModel):
    name: str
    allowed_labels: list[str] = []


class RoleResponse(BaseModel):
    id: int
    name: str
    allowed_labels: list[str]

    class Config:
        from_attributes = True


# --- Version Schemas ---


class PackageLabelsUpdate(BaseModel):
    labels: list[str]


class PackageFileResponse(BaseModel):
    filename: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class PackageVersionResponse(BaseModel):
    version: str
    created_at: datetime
    is_yanked: bool
    # On intègre l'info de l'uploader
    uploader: UserResponse | None = None
    download_count: int = 0
    files: list[PackageFileResponse] = []

    class Config:
        from_attributes = True


# --- Package Schemas ---


class PackageResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    # On pourra afficher la liste des versions directement
    versions: list[PackageVersionResponse] = []
    total_downloads: int = 0

    class Config:
        from_attributes = True


class TokenGenerateRequest(BaseModel):
    """Permet à un admin de spécifier l'utilisateur cible."""

    target_username: Optional[str] = None


class TokenGenerateResponse(BaseModel):
    token: str
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
