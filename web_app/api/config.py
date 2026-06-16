#!/usr/bin/env python3
"""
Application configuration for Osprey API
Supports both settings.py module and environment variables
Environment variables take precedence over settings.py values
"""

import os

try:
    import settings as settings_module
except ImportError:
    settings_module = None


class Config:
    """Application configuration class."""

    DEBUG = os.environ.get('APP_DEBUG', 'False').lower() == 'true'

    DB_HOST = os.environ.get('DB_HOST', getattr(settings_module, 'host', 'localhost'))
    DB_USER = os.environ.get('DB_USER', getattr(settings_module, 'user', 'root'))
    DB_PASSWORD = os.environ.get('DB_PASSWORD', getattr(settings_module, 'password', ''))
    DB_DATABASE = os.environ.get('DB_NAME', getattr(settings_module, 'database', 'osprey'))
    DB_PORT = int(os.environ.get('DB_PORT', getattr(settings_module, 'port', 3306)))

    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        getattr(settings_module, 'secret_key', 'dev-key-change-me-in-production'),
    )

    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FOLDER = getattr(settings_module, 'log_folder', './logs') if settings_module else './logs'
    CACHE_FOLDER = getattr(settings_module, 'cache_folder', './cache') if settings_module else './cache'

    ASPACE_API_ENDPOINT = os.environ.get(
        'ASPACE_API',
        getattr(settings_module, 'aspace_api', None) if settings_module else None,
    )
    ASPACE_API_USERNAME = os.environ.get(
        'ASPACE_USER',
        getattr(settings_module, 'aspace_api_username', None) if settings_module else None,
    )
    ASPACE_API_PASSWORD = os.environ.get(
        'ASPACE_PASSWORD',
        getattr(settings_module, 'aspace_api_password', None) if settings_module else None,
    )

    SITE_VER = getattr(settings_module, 'site_ver', '2.11.1') if settings_module else '2.11.1'
    SITE_ENV = getattr(settings_module, 'env', 'dev') if settings_module else 'dev'


config = Config()
