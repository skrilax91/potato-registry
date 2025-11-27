import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type
from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# ---------------------------------------------------------
# Sous-modèles (Tous les champs ont une valeur par défaut)
# ---------------------------------------------------------


class StorageSettings(BaseModel):
    path: Path = Path("./storage")


class DatabaseSettings(BaseModel):
    url: str = "sqlite://db.sqlite3"


class AppSettings(BaseModel):
    title: str = "Mon Registre Entreprise"
    debug: bool = False
    # Valeur par défaut non sécurisée, à surcharger en prod via ENV ou YAML
    secret_key: str = "insecure-default-secret-change-me"

    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60  # 1 heure par défaut


class AuthSettings(BaseModel):
    local_enabled: bool = True


class OIDCSettings(BaseModel):
    enabled: bool = False
    display_name: str = "SSO Login"

    # Optionnels car si enabled=False, on ne s'en sert pas
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    scopes: str = "openid profile email"

    # Valeurs par défaut standard
    username_claim: str = "preferred_username"
    email_claim: str = "email"

    allow_account_linking: bool = False


# ---------------------------------------------------------
# Modèle Principal & Logique de Chargement
# ---------------------------------------------------------


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """
    Tente de charger 'config.yaml' (ou autre via env var).
    Si le fichier n'existe pas, retourne un dictionnaire vide
    (ne plante pas, laisse les valeurs par défaut s'appliquer).
    """

    def get_field_value(self, field: Field, field_name: str) -> Tuple[Any, str, bool]:
        return super().get_field_value(field, field_name)

    def __call__(self) -> Dict[str, Any]:
        config_file = os.getenv("CONFIG_FILE", "config.yaml")
        path = Path(config_file)

        if not path.exists():
            return {}

        try:
            with path.open("r", encoding="utf-8") as f:
                # Si le fichier est vide, yaml.safe_load retourne None -> on renvoie {}
                return yaml.safe_load(f) or {}
        except Exception as e:
            # En cas d'erreur de lecture (ex: YAML mal formé), on log (print pour l'instant)
            # et on continue pour ne pas crasher l'app
            print(f"⚠️  Erreur lors de la lecture de {config_file}: {e}")
            return {}


class Settings(BaseSettings):
    app: AppSettings = AppSettings()
    storage: StorageSettings = StorageSettings()
    database: DatabaseSettings = DatabaseSettings()
    auth: AuthSettings = AuthSettings()
    oidc: OIDCSettings = OIDCSettings()

    model_config = SettingsConfigDict(
        env_nested_delimiter="__", env_prefix="REGISTRY_", extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
        )


# Instanciation unique
settings = Settings()

# Création automatique du dossier de stockage au démarrage
try:
    settings.storage.path.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"⚠️ Impossible de créer le dossier de stockage {settings.storage.path}: {e}")
