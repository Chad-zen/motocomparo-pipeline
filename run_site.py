"""Start the v2 site locally.

    .venv/Scripts/python.exe run_site.py

Then open http://127.0.0.1:8000 in a browser. Ctrl+C stops it.
`src` is put on the path here so the site runs straight from the repository,
with no install step.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("mcsite.app:app", host="127.0.0.1", port=8000, reload=False)
