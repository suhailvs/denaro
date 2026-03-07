import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "denaro-dev-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
    "rest_framework",
    "core.apps.CoreConfig",
    "transactions.apps.TransactionsConfig",
    "wallets.apps.WalletsConfig",
    "node_api.apps.NodeApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "node_api.middleware.NodeNetworkMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.dummy"
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
APPEND_SLASH = False

REST_FRAMEWORK = {
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_THROTTLE_RATES": {
        "sync": "10/minute",
        "address_info": "2/second",
        "add_node": "10/minute",
        "transaction": "2/second",
        "block": "30/minute",
        "blocks": "10/minute",
    },
}
