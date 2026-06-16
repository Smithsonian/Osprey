#!/usr/bin/env python3
"""Legacy entry point — runs the unified Flask app (dashboard + API blueprint)."""

from app import app

if __name__ == '__main__':
    app.run(threaded=False, debug=True)
