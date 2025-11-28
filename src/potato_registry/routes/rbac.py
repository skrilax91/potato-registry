# src/potato_registry/routes/rbac.py
from fastapi import APIRouter, HTTPException
from typing import List
from src.potato_registry.models import Role, User, Package
from src.potato_registry.schemas import (
    RoleCreate,
    RoleResponse,
    UserRoleAssign,
    PackageLabelsUpdate,
)
from fastapi.params import Depends
from src.potato_registry.core.deps import get_current_admin_jwt_user

router = APIRouter(prefix="/api/rbac", tags=["RBAC (Admin)"])


# --- ROLES ---
@router.post("/roles", response_model=RoleResponse)
async def create_role(
    role_in: RoleCreate, _: User = Depends(get_current_admin_jwt_user)
):
    # On crée le rôle directement avec sa liste de strings
    role = await Role.create(name=role_in.name, allowed_labels=role_in.allowed_labels)
    return role


@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(_: User = Depends(get_current_admin_jwt_user)):
    return await Role.all()


# --- ASSIGNATION USER -> ROLES ---
@router.post("/users/{user_id}/roles")
async def assign_roles_to_user(
    user_id: int, assign: UserRoleAssign, _: User = Depends(get_current_admin_jwt_user)
):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    roles = await Role.filter(id__in=assign.role_ids)
    await user.roles.clear()
    await user.roles.add(*roles)
    return {"status": "success"}


# --- ASSIGNATION PACKAGE -> LABELS ---
@router.put("/packages/{package_name}/labels")
async def update_package_labels(
    package_name: str,
    update: PackageLabelsUpdate,
    _: User = Depends(get_current_admin_jwt_user),
):
    pkg = await Package.get_or_none(name=package_name)
    if not pkg:
        raise HTTPException(status_code=404, detail="Paquet introuvable")

    # On écrase la liste existante par la nouvelle
    pkg.labels = update.labels
    await pkg.save()

    return {"status": "success", "labels": pkg.labels}
