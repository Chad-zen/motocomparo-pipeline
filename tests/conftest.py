"""Load .env before any test runs, so DB-backed tests see DATABASE_URL the
same way the CLI does (mcpipe/cli.py calls this too)."""

from dotenv import load_dotenv

load_dotenv()
