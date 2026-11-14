"""
api/ — the HTTP face of ChargebackLens.

The logic lives in app/scoring.py, app/economics.py and app/explain.py and is
imported from there unchanged. Those modules import each other by bare name
(`from scoring import ...`), which is how Streamlit runs them, so app/ has to be
on sys.path before anything in this package imports them.
"""

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
