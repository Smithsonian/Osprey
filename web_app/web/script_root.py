"""Serve the app under a sub-path (settings.app_root).

Sets the WSGI SCRIPT_NAME so url_for, redirects, static files and the
session cookie path all carry the prefix. Use request.script_root where a
URL has to be built by hand (SQL-built links, JS data attributes).
"""


def normalize_prefix(prefix):
    """Return '' for the domain root, else '/sub/path' with no trailing slash."""
    prefix = (prefix or '').strip().strip('/')
    return '/' + prefix if prefix else ''


class ScriptRootMiddleware:
    """Mount the wrapped WSGI app under a fixed prefix.

    Works whether or not the front-end server strips the prefix before
    handing the request over: a PATH_INFO that still starts with the prefix
    has it removed, anything else is passed through unchanged.
    """

    def __init__(self, wsgi_app, prefix):
        self.wsgi_app = wsgi_app
        self.prefix = normalize_prefix(prefix)

    def __call__(self, environ, start_response):
        prefix = self.prefix
        if prefix:
            path = environ.get('PATH_INFO', '')
            if path == prefix or path.startswith(prefix + '/'):
                environ['PATH_INFO'] = path[len(prefix):] or '/'
            environ['SCRIPT_NAME'] = prefix
        return self.wsgi_app(environ, start_response)
