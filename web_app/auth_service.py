#!/usr/bin/env python3
#
# Dedicated Auth Service Module for Osprey.
# LDAP authentication is only used on internal deployments (site_net="internal").

import time

from flask_login import UserMixin

import settings
from logger import logger


class AuthBaseUser(UserMixin):
    """Base class for users authenticated via external services."""
    def __init__(self, name, id, full_name, active=True):
        self.name = name
        self.id = id
        self.full_name = full_name
        self.active = active

    def get_id(self):
        return self.name

    @property
    def is_active(self):
        return self.active

    @property
    def is_anonymous(self):
        return False

    @property
    def is_authenticated(self):
        return self.id is not None and bool(self.active)


class AuthService:
    """LDAP authentication for internal Osprey deployments."""

    def __init__(self):
        from ldap3 import Server, ALL
        self.server = Server(settings.ldap_server, port=636, use_ssl=True, get_info=ALL)
        self.conn = None
        self.bound = False

    def connect(self):
        """Establishes and returns a fresh LDAP connection (without binding)."""
        from ldap3 import Connection
        if self.conn is None:
            self.conn = Connection(self.server, auto_bind=False)
        return self.conn

    def close_connection(self):
        """Explicitly closes the underlying LDAP connection resource."""
        if self.conn:
            try:
                self.conn.unbind()
            except Exception:
                pass
            finally:
                self.conn = None
                self.bound = False

    def authenticate_user(self, username: str, password: str) -> bool:
        """
        Authenticates a user against LDAP with encoding fallback (utf-8 -> latin-1).
        Returns True on success, False on failure.
        """
        from ldap3 import Connection, set_config_parameter
        from ldap3.core.exceptions import LDAPBindError

        if not password or not str(password).strip():
            logger.error("LDAP: empty password rejected for {}".format(username))
            return False

        try:
            set_config_parameter('DEFAULT_SERVER_ENCODING', 'utf-8')
            conn = Connection(self.server, user=username, password=password, auto_bind=True)
            logger.info("LDAP bind succeeded for {}".format(username))
            self.bound = True
            return True
        except LDAPBindError:
            time.sleep(3)
            logger.info("LDAP trying latin-1 for {}".format(username))
            set_config_parameter('DEFAULT_SERVER_ENCODING', 'latin-1')
            try:
                conn = Connection(self.server, user=username, password=password, auto_bind=True)
                logger.info("LDAP latin-1 bind succeeded for {}".format(username))
                self.bound = True
                return True
            except LDAPBindError as e:
                logger.error("LDAP bind failed for {}".format(username))
                return False


_ldap_service = None


def get_auth_service():
    """Return the LDAP auth service singleton (internal deployments only)."""
    global _ldap_service
    if _ldap_service is None:
        _ldap_service = AuthService()
    return _ldap_service
