"""Prepare a user-supplied MIRACL Thai snapshot without committing it."""

from __future__ import annotations

import argparse
from pathlib import Path

from prepare_utils import prepare_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Local upstream file or HTTPS URL.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    digest = prepare_source(args.source, args.output, args.expected_sha256)
    print(f"prepared={args.output} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
