from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from src.potato_registry.core.config import settings
from src.potato_registry.models import DownloadLog, PackageFile, Package

router = APIRouter(prefix="/simple", tags=["Simple Index (PEP 503)"])


@router.get("/", response_class=HTMLResponse)
async def list_packages():
    """
    Filtrage simple basé sur les listes JSON.
    """
    # 1. Simuler l'utilisateur courant (À remplacer par l'auth bientôt)
    # Imaginons que l'utilisateur a le rôle "Dev" qui a allowed_labels=["public", "interne"]
    user_allowed_labels = {"public", "interne"}

    # 2. Récupérer tous les paquets
    # Note: On récupère juste l'ID, le nom et les labels pour être léger
    all_packages = await Package.all().values("name", "labels")

    visible_packages = []
    for pkg in all_packages:
        pkg_labels = set(pkg["labels"])  # Convertir la liste JSON en set

        # 3. INTERSECTION
        # Si l'intersection n'est pas vide, l'utilisateur a au moins un label en commun
        if not pkg_labels or not pkg_labels.isdisjoint(user_allowed_labels):
            visible_packages.append(pkg["name"])

    # 4. Génération HTML
    if not visible_packages:
        return "<html><body>No packages available.</body></html>"

    links = "".join([f'<a href="{name}/">{name}</a><br>' for name in visible_packages])
    return f"""
    <html>
        <head><title>Simple Index</title></head>
        <body>
            <h1>Package Index</h1>
            {links}
        </body>
    </html>
    """


@router.get("/{package_name}/", response_class=HTMLResponse)
async def package_details(package_name: str, request: Request):
    """Liste les versions d'un paquet."""
    user_allowed_labels = {"public", "interne"}

    pkg = await Package.get_or_none(name=package_name)

    if not pkg or set(pkg.labels) and set(pkg.labels).isdisjoint(user_allowed_labels):
        raise HTTPException(status_code=404, detail="Paquet introuvable")

    files = await PackageFile.filter(version__package=pkg).all()

    links = ""
    for f in files:
        # PEP 503 : <a href="filename">filename</a>
        links += f'<a href="{f.filename}">{f.filename}</a><br>\n'

    return f"""
    <html>
        <head><title>Links for {package_name}</title></head>
        <body>
            <h1>Links for {package_name}</h1>
            {links}
        </body>
    </html>
    """


async def log_download(pkg_file_id: int, user_agent: str, ip: str):
    pkg_file = await PackageFile.get_or_none(id=pkg_file_id)

    if pkg_file:
        await DownloadLog.create(
            package_file=pkg_file,
            user_agent=user_agent[:255] if user_agent else None,
            ip=ip,
        )


@router.get("/{package_name}/{filename}")
async def get_package_file(
    package_name: str,
    filename: str,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Sert le fichier SI l'utilisateur a le label requis.
    """
    # 1. Vérification DB et Droits
    # On joint les tables pour remonter au Paquet et vérifier ses labels
    pkg_file = await PackageFile.get_or_none(filename=filename).prefetch_related(
        "version__package"
    )

    # Si fichier inconnu
    if not pkg_file:
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    # Récupération du paquet parent
    pkg = pkg_file.version.package

    # SÉCURITÉ : Vérification des labels
    user_labels = {"public", "interne"}

    if set(pkg.labels) and set(pkg.labels).isdisjoint(user_labels):
        # L'utilisateur n'a pas le droit de télécharger ce fichier
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    # 2. Vérification Physique
    file_path = settings.storage.path / package_name / filename
    if not file_path.exists():
        # Incohérence DB vs Disque
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque")

    # 3. Logging Async (On passe l'ID, c'est plus sûr pour les tâches de fond)
    background_tasks.add_task(
        log_download,
        pkg_file_id=pkg_file.id,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host,
    )

    return FileResponse(
        path=file_path, filename=filename, media_type="application/octet-stream"
    )
