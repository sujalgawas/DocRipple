"""Vercel Python entrypoint.

Vercel routes every request here (see ``vercel.json``) and expects a
module-level ASGI application named ``app``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ``src`` lives one level above this file. Vercel's builder normally adds the
# project root to sys.path, but inserting it explicitly keeps imports working
# for local ``vercel dev`` runs and custom framework presets alike.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.main import app

__all__ = ["app"]
