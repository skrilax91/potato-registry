# src/potato_registry/routes/sso.py
import secrets
import time
from jose import JWTError, jwt, jws
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse
import httpx  # Pour les requêtes HTTP asynchrones

from src.potato_registry.models import User  # Pour la création/mise à jour
from src.potato_registry.core.config import settings
from src.potato_registry.core.security import (
    create_access_token,
)  # Pour la session locale
from src.potato_registry.core.sso import (
    STATE_TTL_SECONDS,
    check_and_clear_state,
    get_jwks_key,
    get_oidc_metadata,
    STATE_CACHE,
)

router = APIRouter(prefix="/sso", tags=["SSO (OIDC)"])


# -------------------------------------------------------------
# 1. /login - Lancement du flux OIDC
# -------------------------------------------------------------
@router.get("/login")
async def sso_login(request: Request):
    if not settings.oidc.enabled or not settings.oidc.issuer_url:
        raise HTTPException(status_code=503, detail="SSO non configuré.")

    metadata = await get_oidc_metadata()
    auth_endpoint = metadata["authorization_endpoint"]

    # URL de redirection (où Keycloak/IdP renverra l'utilisateur)
    redirect_uri = str(request.base_url).rstrip("/") + router.prefix + "/callback"

    state_secret = secrets.token_urlsafe(32)
    STATE_CACHE[state_secret] = int(time.time()) + STATE_TTL_SECONDS

    # Construction de l'URL de connexion
    auth_url = (
        f"{auth_endpoint}"
        f"?client_id={settings.oidc.client_id}"
        f"&response_type=code"
        f"&scope={settings.oidc.scopes}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state_secret}"
    )

    return RedirectResponse(auth_url)


# -------------------------------------------------------------
# 2. /callback - Réception du code et échange de tokens
# -------------------------------------------------------------
@router.get("/callback")
async def sso_callback(request: Request, code: str, state: str):
    check_and_clear_state(state)

    redirect_uri = str(request.base_url).rstrip("/") + router.prefix + "/callback"

    metadata = await get_oidc_metadata()
    token_endpoint = metadata["token_endpoint"]

    # Étape 2 : Échange du code d'autorisation contre les tokens
    async with httpx.AsyncClient() as client:
        token_data = {
            "grant_type": "authorization_code",
            "client_id": settings.oidc.client_id,
            "client_secret": settings.oidc.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        response = await client.post(token_endpoint, data=token_data)

        if response.status_code != 200:
            raise HTTPException(
                status_code=500, detail="Échec de l'échange de tokens avec l'IdP."
            )

        tokens = response.json()
        id_token = tokens.get("id_token")

        if not id_token:
            raise HTTPException(status_code=500, detail="ID Token manquant.")

    try:
        header = jws.get_unverified_header(id_token)
        kid = header.get("kid")

        if not kid:
            raise JWTError(
                "KID (Key ID) manquant dans le jeton ID. Le jeton n'est pas signé correctement."
            )

        # B. Récupérer la clé publique correspondante (cache et récupération JWKS)
        key = await get_jwks_key(kid)

        # C. Valider la signature et décoder le jeton
        claims = jwt.decode(
            id_token,
            key,  # <--- LA CLÉ PUBLIQUE RÉCUPÉRÉE
            algorithms=[header.get("alg", "RS256")],  # Utilise l'algo du header
            audience=settings.oidc.client_id,  # Vérifie que le jeton est pour nous
            issuer=settings.oidc.issuer_url.rstrip("/"),  # Vérifie l'émetteur
            options={"verify_at_hash": False},
        )

    except JWTError as e:
        # Erreur si la signature ne correspond pas, si le jeton est expiré, ou si l'audience/émetteur est faux
        print(f"Échec de la validation de la signature JWT : {e}")
        raise HTTPException(
            status_code=401, detail=f"ID Token invalide ou non vérifiable : {e}"
        )
    except HTTPException:
        # Renvoie les erreurs 401/503 levées par get_jwks_key
        raise

    # Étape 4 : Mappage des claims et gestion de l'utilisateur
    username_claim = claims.get(settings.oidc.username_claim)
    email_claim = claims.get(settings.oidc.email_claim)

    if not username_claim or not email_claim:
        raise HTTPException(status_code=400, detail="Claims de connexion manquants.")

    # LOGIQUE DE PROVISIONING (Création ou Mise à jour)
    user = await provision_sso_user(username=username_claim, email=email_claim)

    # Étape 5 : Création de la session locale (JWT)
    access_token = create_access_token(data={"username": user.username})

    # Normalement, on redirige vers le front-end avec le token dans l'URL/Cookie
    # Ici, on renvoie juste le token pour le test
    return {"message": "Connexion SSO réussie", "access_token": access_token}


# -------------------------------------------------------------
# 3. Logique de Provisioning (Création ou Mise à jour)
# -------------------------------------------------------------
async def provision_sso_user(username: str, email: str) -> User:
    """Crée ou met à jour un utilisateur en fonction des règles SSO."""

    sso_user = await User.get_or_none(username=username)

    # Règle : Utilisateur existe déjà via SSO/Local
    if sso_user:
        if not sso_user.is_sso_managed and not settings.oidc.allow_account_linking:
            # Cas 0 : L'utilisateur local existe déjà mais n'est pas SSO-managed
            raise HTTPException(
                status_code=403,
                detail="Un utilisateur local existe déjà avec ce nom d'utilisateur.",
            )

        sso_user.is_sso_managed = True
        sso_user.email = email
        await sso_user.save()
        return sso_user

    # Règle : L'utilisateur n'existe pas encore
    # ---------------------------------------

    # 1. Vérification par email (Règle d'Account Linking)
    local_user_by_email = await User.get_or_none(email=email)

    if local_user_by_email:
        # L'email existe déjà, mais l'username est nouveau
        if settings.oidc.allow_account_linking:
            # Cas 1.1 : Lier le compte local à l'identité SSO
            local_user_by_email.username = (
                username  # Mettre à jour l'username avec le claim SSO
            )
            local_user_by_email.is_sso_managed = True
            # Son mot de passe local/pip_token est conservé pour la compatibilité Basic Auth
            await local_user_by_email.save()
            return local_user_by_email
        else:
            # Cas 1.2 : Refuser l'accès pour éviter l'usurpation (policy stricte)
            raise HTTPException(
                status_code=403,
                detail="Compte local existant trouvé, liaison désactivée.",
            )

    # 2. Création pure d'un nouvel utilisateur SSO
    return await User.create(
        username=username,
        email=email,
        is_active=True,
        is_sso_managed=True,
    )
