from pathlib import Path
from tortoise.contrib.fastapi import register_tortoise

from fastapi import FastAPI
from .core.config import settings
from .routes import simple, upload, users, packages, rbac
from .core.utils import get_app_version

# Configuration
STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app.title, version=get_app_version())

app.include_router(simple.router)
app.include_router(upload.router)
app.include_router(users.router)
app.include_router(packages.router)
app.include_router(rbac.router)

register_tortoise(
    app,
    db_url=settings.database.url,
    modules={
        "models": ["src.potato_registry.models"]
    },  # Pointe vers notre fichier models.py
    generate_schemas=True,  # En DEV uniquement : crée les tables automatiquement
    add_exception_handlers=True,
)


@app.get("/health")
def health_check():
    """Permet à Docker/K8s de savoir si l'app est en vie"""
    return {
        "status": "ok",
        "app": settings.app.title,
        "storage": str(settings.storage.path),
    }
