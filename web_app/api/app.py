#!/usr/bin/env python3
"""Legacy entry point — runs the unified Flask app (dashboard + API blueprint)."""

import settings
from app import app

if __name__ == '__main__':
    app.run(threaded=False, debug=(settings.env == "dev"))
