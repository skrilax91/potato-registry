# ----------------------------------------------------------------------
# ÉTAPE 1 : BUILDER (Installation des dépendances)
# ----------------------------------------------------------------------
# Utilisation de Python 3.14 (Scénario Novembre 2025)
FROM python:3.14-slim AS builder 

# Définition des variables d'environnement
ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Répertoire de travail
WORKDIR /app

# Copie des fichiers de configuration
COPY pyproject.toml uv.lock /app/

# Installation des dépendances système (Pour PostgreSQL et outils de base)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Installe uv et toutes les dépendances de production
RUN pip install uv uvicorn && uv sync --no-dev


FROM python:3.14-slim AS final

WORKDIR /app

# Copie du code source
COPY src/ /app/src/

COPY --from=builder /app/.venv/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# Création du dossier de stockage persistant
RUN mkdir -p storage

EXPOSE 8000

# Commande de démarrage (uvicorn)
CMD ["python", "-m", "uvicorn", "src.potato_registry.main:app", "--host", "0.0.0.0", "--port", "8000"]