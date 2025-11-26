# src/mon_registre/models.py
from tortoise import fields, models


class User(models.Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True, index=True)
    email = fields.CharField(max_length=255, null=True)

    # Sécurité
    hashed_password = fields.CharField(max_length=128, null=True)

    # Flags / Rôles
    is_active = fields.BooleanField(default=True)
    is_superuser = fields.BooleanField(default=False)
    is_service_account = fields.BooleanField(default=False)
    is_sso_managed = fields.BooleanField(default=False)

    # Tracking
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)
    last_login_at = fields.DatetimeField(null=True)

    roles = fields.ManyToManyField(
        "models.Role", related_name="users", through="user_roles"
    )

    class Meta:
        table = "users"

    def __str__(self):
        return self.username


class Role(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=50, unique=True)

    # ex: ["public", "interne", "team-data"]
    allowed_labels = fields.JSONField(default=list)

    users: fields.ReverseRelation["User"]

    class Meta:
        table = "roles"


##### Modèles pour les paquets #####


class Package(models.Model):
    """
    Représente un projet (ex: 'mon-super-paquet').
    Il n'a pas de propriétaire, c'est juste un conteneur de versions.
    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, unique=True, index=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    labels = fields.JSONField(default=list)

    # Relation inverse
    versions: fields.ReverseRelation["PackageVersion"]

    class Meta:
        table = "packages"


class PackageVersion(models.Model):
    """
    Représente une version spécifique (ex: '1.0.2').
    C'est ici qu'on sait QUI a poussé cette version.
    """

    id = fields.IntField(pk=True)

    # Liens
    package = fields.ForeignKeyField("models.Package", related_name="versions")
    uploader = fields.ForeignKeyField(
        "models.User", related_name="uploaded_versions", null=True
    )

    # Métadonnées
    version = fields.CharField(max_length=50)
    is_yanked = fields.BooleanField(default=False)  # Si une version est retirée
    yanked_reason = fields.CharField(max_length=255, null=True)

    created_at = fields.DatetimeField(auto_now_add=True)

    downloads: fields.ReverseRelation["DownloadLog"]
    files: fields.ReverseRelation["PackageFile"]

    class Meta:
        table = "package_versions"
        # On s'assure qu'on ne peut pas avoir deux fois la version 1.0 pour le même paquet
        unique_together = (("package", "version"),)


class PackageFile(models.Model):
    """
    Représente un fichier physique (.whl, .tar.gz).
    Une version peut avoir plusieurs fichiers.
    """

    id = fields.IntField(pk=True)
    version = fields.ForeignKeyField("models.PackageVersion", related_name="files")

    filename = fields.CharField(max_length=255, unique=True, index=True)

    # On peut ajouter le hash ici plus tard (sha256)
    created_at = fields.DatetimeField(auto_now_add=True)

    # Les logs sont liés au FICHIER téléchargé, pas juste à la version
    downloads: fields.ReverseRelation["DownloadLog"]

    class Meta:
        table = "package_files"


class DownloadLog(models.Model):
    """
    Table dédiée aux stats de téléchargement (haute volumétrie).
    """

    id = fields.IntField(pk=True)
    package_file = fields.ForeignKeyField(
        "models.PackageFile", related_name="downloads"
    )

    timestamp = fields.DatetimeField(auto_now_add=True)
    user_agent = fields.CharField(max_length=255, null=True)
    ip_address = fields.CharField(max_length=50, null=True)

    class Meta:
        table = "download_logs"
