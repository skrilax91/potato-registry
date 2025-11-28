# src/potato_registry/core/initial_data.py
from src.potato_registry.models import User
from src.potato_registry.core.config import settings
from src.potato_registry.core.security import get_password_hash
from tortoise.exceptions import DoesNotExist


async def create_initial_admin_user():
    """
    Crée un utilisateur administrateur initial si configuré et s'il n'existe pas.
    """

    admin_settings = settings.app.admin

    username = admin_settings.initial_username
    password = admin_settings.initial_password
    email = admin_settings.initial_email

    # Vérification des prérequis de configuration
    if not username or not password:
        print(
            "INFO: Les variables d'environnement pour l'administrateur initial (username/password) ne sont pas définies. Passage."
        )
        return

    try:
        # Tente de trouver l'utilisateur par son nom
        await User.get(username=username)
        print(
            f"INFO: L'utilisateur administrateur '{username}' existe déjà. Aucune action nécessaire."
        )
        return
    except DoesNotExist:
        # L'utilisateur n'existe pas, on le crée.
        print(f"INFO: Création de l'utilisateur administrateur initial '{username}'...")

        # Hachage du mot de passe
        hashed_password = get_password_hash(password)

        # Création de l'utilisateur
        await User.create(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=True,
        )
        print(f"SUCCÈS: L'utilisateur administrateur '{username}' a été créé.")
    except Exception as e:
        print(f"ERREUR: Échec de la création de l'utilisateur initial : {e}")
