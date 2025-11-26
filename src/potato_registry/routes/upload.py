# src/mon_registre/routes/upload.py
import shutil
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from src.potato_registry.core.config import settings
from src.potato_registry.models import Package, PackageVersion, PackageFile
from tortoise.transactions import in_transaction

router = APIRouter(tags=["Upload Legacy"])


@router.post("/")
async def upload_package(
    name: str = Form(...), version: str = Form(...), content: UploadFile = File(...)
):
    safe_name = name.lower().replace("_", "-")

    async with in_transaction():
        package_obj, created = await Package.get_or_create(name=safe_name)

        version_obj, _ = await PackageVersion.get_or_create(
            package=package_obj,
            version=version,
            defaults={"uploader": None},
        )

        file_exists = await PackageFile.filter(
            version=version_obj, filename=content.filename
        ).exists()

        if file_exists:
            raise HTTPException(
                status_code=409, detail=f"Le fichier {content.filename} existe déjà."
            )

        # 3. Écriture sur le disque (Storage)
        final_dir = settings.storage.path / safe_name
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / content.filename

        try:
            with final_path.open("wb") as buffer:
                shutil.copyfileobj(content.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur écriture fichier: {e}")
        finally:
            content.file.close()
        await PackageFile.create(version=version_obj, filename=content.filename)
    return {"status": "success", "filename": content.filename, "version": version}
