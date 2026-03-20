"""VHP Backend Launcher — run from backend/ with: python main.py"""

import sys
from pathlib import Path

# Add src/ and data/ to Python path
_backend = Path(__file__).resolve().parent
for p in [_backend / "src", _backend / "data"]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
