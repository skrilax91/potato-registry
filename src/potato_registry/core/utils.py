from importlib import metadata


def get_app_version() -> str:
    """
    Récupère la version installée du projet.
    Fonctionne si le projet a été installé (pip install . / uv sync)
    """
    try:
        # Remplace 'mon-registre' par le nom défini dans ton pyproject.toml [project] name
        return metadata.version("mon-registre")
    except metadata.PackageNotFoundError:
        # Fallback si lancé sans installation (ex: script brut)
        return "0.0.0-dev"
