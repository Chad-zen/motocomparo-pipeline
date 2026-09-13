"""Start the v2 site locally.

    .venv/Scripts/python.exe run_site.py          # this computer only
    .venv/Scripts/python.exe run_site.py --lan    # also phones on the same wifi

Ctrl+C stops it. `src` is put on the path here so the site runs straight from
the repository, with no install step.

`--lan` binds every interface instead of the loopback, so anything on the local
network can open it — useful for reading a page on a phone, which is where a
catalogue actually gets read. It is a development convenience and nothing more:
the site has no authentication, so only turn it on at home, and never on a
network you do not control. Windows Firewall asks once; allow private networks
only.
"""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def _local_ip() -> str:
    """This machine's address on its own network, for the hint printed below."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # sends nothing; this only picks a route
        return str(s.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    import uvicorn

    lan = "--lan" in sys.argv
    host = "0.0.0.0" if lan else "127.0.0.1"  # noqa: S104 — deliberate, see docstring

    if lan:
        print()
        print("  sur ce PC      http://127.0.0.1:8000")
        print(f"  sur le mobile  http://{_local_ip()}:8000")
        print()

    uvicorn.run("mcsite.app:app", host=host, port=8000, reload=False)
