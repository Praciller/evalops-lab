#!/usr/bin/env python3
"""Export the FastAPI Workspace OpenAPI schema to apps/workspace/openapi.json.

Usage:
    python scripts/export_workspace_openapi.py           # write mode
    python scripts/export_workspace_openapi.py --check   # check mode (CI)

The generated schema is canonical JSON (sorted keys, trailing newline).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

OUTPUT_PATH = repo_root / "apps" / "workspace" / "openapi.json"


def generate_schema() -> str:
    from evalops.workspace.api.app import create_workspace_app
    from evalops.workspace.security import BootstrapSessionManager, WorkspaceOrigin
    from evalops.workspace.storage import WorkspaceStore

    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(Path(tmp) / "root")
        manager = BootstrapSessionManager(bootstrap_nonce="schema-export")
        origin = WorkspaceOrigin(host="127.0.0.1", port=8000)
        # Re-enable openapi endpoint for export only
        app = create_workspace_app(store, manager, origin)
        # Patch openapi_url temporarily for schema generation
        app.openapi_url = "/openapi.json"
        schema = app.openapi()
        return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export workspace OpenAPI schema.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: fail if openapi.json does not match generated schema.",
    )
    args = parser.parse_args()

    generated = generate_schema()

    if args.check:
        if not OUTPUT_PATH.is_file():
            print(
                f"ERROR: {OUTPUT_PATH} does not exist. Run without --check to generate.",
                file=sys.stderr,
            )
            return 1
        existing = OUTPUT_PATH.read_text(encoding="utf-8")
        if existing != generated:
            print(
                "ERROR: apps/workspace/openapi.json is out of sync with the FastAPI app.\n"
                "Run: python scripts/export_workspace_openapi.py",
                file=sys.stderr,
            )
            return 1
        print("OK: openapi.json matches the FastAPI app.")
        return 0

    OUTPUT_PATH.write_text(generated, encoding="utf-8")
    print(f"Written: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
