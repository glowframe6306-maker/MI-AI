from importlib import import_module
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYTHONPATH", str(ROOT))

app_module = import_module("backend.app")

app = app_module.app
application = app
handler = app