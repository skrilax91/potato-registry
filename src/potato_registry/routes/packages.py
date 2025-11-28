# src/potato_registry/routes/packages.py
from fastapi import APIRouter, HTTPException
from typing import List

from src.potato_registry.models import Package, PackageVersion
from tortoise.functions import Count
from itertools import groupby
from src.potato_registry.schemas import (
    PackageResponse,
    PackageVersionResponse,
    PackageFileResponse,
)
from src.potato_registry.core.config import settings
import shutil
from fastapi.params import Depends
from src.potato_registry.core.deps import (
    get_current_admin_jwt_user,
    get_current_jwt_only_user,
)
from src.potato_registry.models import User

router = APIRouter(prefix="/api/packages", tags=["Packages Management (Admin)"])


@router.get("/", response_model=List[PackageResponse])
async def list_packages(_: User = Depends(get_current_jwt_only_user)):
    """Liste tous les paquets avec leurs versions et les auteurs."""
    versions_query = (
        await PackageVersion.all()
        .annotate(download_count=Count("files__downloads"))
        .prefetch_related(
            "package",
            "uploader",
        )
        .order_by("package__name", "-created_at")
    )

    response_data = []

    for package_name, versions_iter in groupby(
        versions_query, key=lambda x: x.package.name
    ):
        versions_list = list(versions_iter)

        package_obj = versions_list[0].package
        total_downloads = sum(v.download_count for v in versions_list)

        response_data.append(
            PackageResponse(
                id=package_obj.id,
                name=package_obj.name,
                created_at=package_obj.created_at,
                total_downloads=total_downloads,
                versions=[
                    PackageVersionResponse(
                        version=v.version,
                        created_at=v.created_at,
                        is_yanked=v.is_yanked,
                        download_count=v.download_count,
                        uploader=v.uploader,
                    )
                    for v in versions_list
                ],
            )
        )
    return response_data


@router.get("/{name}", response_model=PackageResponse)
async def get_package(name: str, _: User = Depends(get_current_jwt_only_user)):
    """Récupère les détails d'un paquet spécifique."""
    versions = (
        await PackageVersion.filter(package__name=name)
        .annotate(download_count=Count("files__downloads"))
        .prefetch_related("package", "uploader", "files")
        .order_by("-created_at")
    )

    if not versions:
        raise HTTPException(status_code=404, detail="Paquet introuvable")

    package_obj = versions[0].package
    total_downloads = sum(v.download_count for v in versions)

    return PackageResponse(
        id=package_obj.id,
        name=package_obj.name,
        created_at=package_obj.created_at,
        total_downloads=total_downloads,
        versions=[
            PackageVersionResponse(
                version=v.version,
                created_at=v.created_at,
                is_yanked=v.is_yanked,
                download_count=v.download_count,
                uploader=v.uploader,
                files=[
                    PackageFileResponse(
                        filename=f.filename,
                        uploaded_at=f.created_at,
                    )
                    for f in v.files
                ],
            )
            for v in versions
        ],
    )


@router.delete("/{name}")
async def delete_package(name: str, _: User = Depends(get_current_admin_jwt_user)):
    """
    Supprime un paquet de la DB ET du disque dur.
    """
    # 1. Vérifier si le paquet existe en base
    pkg = await Package.get_or_none(name=name)
    if not pkg:
        raise HTTPException(status_code=404, detail="Paquet introuvable")

    # 2. Supprimer de la Base de Données
    # Le delete en cascade supprimera aussi les versions liées grâce à Tortoise
    await pkg.delete()

    # 3. Supprimer du Stockage Physique
    package_dir = settings.storage.path / name

    if package_dir.exists() and package_dir.is_dir():
        try:
            shutil.rmtree(package_dir)  # Supprime le dossier et tout son contenu
        except Exception as e:
            # On log l'erreur mais on ne plante pas la requête, car la DB est déjà propre
            print(f"⚠️ Erreur lors de la suppression des fichiers pour {name}: {e}")

    return {"message": f"Paquet {name} supprimé définitivement"}
