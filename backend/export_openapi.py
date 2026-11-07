"""Write the API description to docs/openapi.json, so the frontend can see every endpoint and field.
Run from backend/:  .venv/bin/python export_openapi.py"""
import json
import os
from pathlib import Path

os.environ.setdefault("AGENTS_SCHEDULER", "false")
from app.main import app  # noqa: E402

out = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=1, sort_keys=True))
print(f"Wrote {out} ({len(app.openapi()['paths'])} paths)")
