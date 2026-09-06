from django.apps import AppConfig


class StorageConfig(AppConfig):
    name = "apps.storage"
    verbose_name = "Dossiers et fichiers"

    def ready(self):
        from . import signals  # noqa: F401
