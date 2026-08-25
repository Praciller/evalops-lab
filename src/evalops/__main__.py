"""Allow ``python -m evalops`` to invoke the CLI."""

from evalops.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
