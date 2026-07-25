"""Entry point for WoL Dashboard when run as a module: python -m src"""

from .app import app, startup

if __name__ == "__main__":
    startup()
    app.run(host="0.0.0.0", port=5000, debug=False)
