# Cache global pour stocker les métadonnées OIDC
# {
#   "data": Dict[str, Any],
#   "expires_at": int (timestamp)
# }
from typing import Any
import time
from fastapi import HTTPException
from src.potato_registry.core.config import settings
import httpx  # Pour les requêtes HTTP asynchrones
from jose import JWTError, jwk


OIDC_METADATA_CACHE: dict[str, Any] = {}
CACHE_TTL_SECONDS = 3600  # 1 heure de validité pour les métadonnées


async def get_oidc_metadata() -> dict[str, Any]:
    """
    Récupère les métadonnées OIDC à partir de l'URL d'émetteur
    et les met en cache pour éviter les requêtes répétées.
    """
    global OIDC_METADATA_CACHE

    issuer_url = settings.oidc.issuer_url

    if not issuer_url:
        raise HTTPException(
            status_code=503, detail="URL d'émetteur OIDC non configurée."
        )

    # 1. Vérification du cache
    cache_entry = OIDC_METADATA_CACHE.get(issuer_url)
    current_time = int(time.time())

    if cache_entry and cache_entry["expires_at"] > current_time:
        # Cache valide, on retourne les données
        return cache_entry["data"]

    # 2. Récupération à partir de l'IdP
    discovery_url = issuer_url.rstrip("/") + "/.well-known/openid-configuration"

    try:
        async with httpx.AsyncClient() as client:
            # Note: Un IdP peut nécessiter un timeout pour la sécurité
            response = await client.get(discovery_url, timeout=5.0)
            response.raise_for_status()  # Lève une exception si le statut est une erreur (4xx ou 5xx)

            metadata = response.json()

            # Vérification minimale des champs essentiels
            if not all(
                k in metadata
                for k in ["authorization_endpoint", "token_endpoint", "jwks_uri"]
            ):
                raise ValueError(
                    "Les métadonnées OIDC sont incomplètes (endpoints manquants)."
                )

            # 3. Mise à jour du cache
            OIDC_METADATA_CACHE[issuer_url] = {
                "data": metadata,
                "expires_at": current_time + CACHE_TTL_SECONDS,
            }

            return metadata

    except httpx.RequestError as e:
        # Erreur réseau, DNS, timeout...
        raise HTTPException(
            status_code=503,
            detail=f"Échec de la connexion à l'émetteur OIDC ({discovery_url}): {e}",
        )
    except Exception as e:
        # Erreur JSON, valeur manquante...
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du traitement des métadonnées OIDC: {e}",
        )


# Dictionnaire pour simuler le cache de "state" (Anti-CSRF)
# Clé: state_secret (str) ; Valeur: timestamp d'expiration (int)
STATE_CACHE: dict[str, int] = {}
STATE_TTL_SECONDS = 300  # 5 minutes pour valider le state


def check_and_clear_state(state: str) -> None:
    """Vérifie le state CSRF et le supprime du cache s'il est valide."""
    current_time = int(time.time())

    if state not in STATE_CACHE:
        raise HTTPException(status_code=400, detail="State OIDC invalide ou manquant.")

    if STATE_CACHE[state] < current_time:
        del STATE_CACHE[state]
        raise HTTPException(status_code=400, detail="State OIDC expiré.")

    # Le state est valide, on le supprime pour usage unique
    del STATE_CACHE[state]


JWKS_CACHE: dict[str, Any] = {}
JWKS_TTL_SECONDS = 86400  # Cache les clés pendant 24 heures


async def get_jwks_key(kid: str) -> dict[str, Any]:
    """
    Récupère la clé publique JWKS pour le KID donné et la met en cache.
    """
    global JWKS_CACHE

    # 1. Vérification du cache par KID
    cache_entry = JWKS_CACHE.get(kid)
    if cache_entry and cache_entry.get("expires_at", 0) > int(time.time()):
        return cache_entry["key"]

    # 2. Récupération de l'URI JWKS à partir des métadonnées
    try:
        metadata = await get_oidc_metadata()
        jwks_uri = metadata.get("jwks_uri")
        if not jwks_uri:
            raise ValueError("JWKS URI manquant dans la configuration OIDC.")
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Échec de la récupération de l'URI JWKS: {e}"
        )

    # 3. Récupération des clés depuis l'URI
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(jwks_uri)
            response.raise_for_status()
            jwks_data = response.json()

            # 4. Traiter et mettre en cache les clés
            target_key = None

            for key in jwks_data.get("keys", []):
                # Utilise jwk.construct pour parser la clé brute en objet vérifiable
                public_key = jwk.construct(key)

                # Cacher la clé construite
                JWKS_CACHE[key.get("kid")] = {
                    "key": public_key,
                    "expires_at": int(time.time()) + JWKS_TTL_SECONDS,
                }
                if key.get("kid") == kid:
                    target_key = public_key

            if target_key:
                return target_key

            raise JWTError(
                "Clé de vérification (KID) non trouvée pour valider le jeton."
            )

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503, detail=f"Échec de la récupération JWKS: {e}"
        )
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Erreur de validation JWKS: {e}")
