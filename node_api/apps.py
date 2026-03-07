from django.apps import AppConfig

from node_api.network import NodesManager


class NodeApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "node_api"

    def ready(self):
        NodesManager.init()
