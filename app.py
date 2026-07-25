#!/usr/bin/env python3
"""Entry point for WoL Dashboard application.

This is a wrapper that runs the main application from the src package.
Run: python app.py
"""

if __name__ == "__main__":
    from src.app import app, startup
    
    startup()
    app.run(host="0.0.0.0", port=5000, debug=False)