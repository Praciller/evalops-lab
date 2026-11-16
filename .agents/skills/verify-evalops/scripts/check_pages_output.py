"""Verify the file boundary of an assembled local EvalOps Pages export."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PureWindowsPath


def files_under(root: Path) -> set[Path]:
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise ValueError("missing or linked static directory")
    files = set()
    for path in root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError("linked entry in static directory")
        if path.is_file():
            files.add(path.relative_to(root))
        elif not path.is_dir():
            raise ValueError("non-regular entry in static directory")
    return files


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_matching_tree(source: Path, built: Path, paths: set[Path], label: str) -> None:
    require(files_under(built) == paths, f"unexpected or missing file in {label}")
    for path in sorted(paths):
        require(
            (built / path).read_bytes() == (source / path).read_bytes(), f"bytes differ in {label}"
        )


def next_route_files(routes: dict[Path, str]) -> set[Path]:
    # Companion filenames emitted by the pinned Next.js static export.
    files = {Path("404.html"), Path("404/index.html")}
    for route, segment_prefix in routes.items():
        for filename in ("index.html", "index.txt", "__next._full.txt", "__next._tree.txt"):
            files.add(route / filename)
        files.add(route / f"__next.{segment_prefix}__PAGE__.txt")
    return files


def main() -> None:
    web = Path("apps/web")
    public = web / "public"
    out = web / "out"
    public_files = files_under(public)
    evidence = public / "evidence"
    index = Path("index.json")
    require(Path("evidence") / index in public_files, "public evidence index missing")
    artifacts = json.loads((evidence / index).read_text(encoding="utf-8"))["artifacts"]
    expected_evidence = {index}
    route_segments = {
        Path("."): "",
        Path("runs"): "runs.",
        Path("comparisons"): "comparisons.",
        Path("_not-found"): "_not-found.",
    }
    seen_ids: set[str] = set()
    for item in artifacts:
        artifact_id = item["artifact_id"]
        require(
            bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", artifact_id))
            and not artifact_id.endswith("."),
            "invalid ID",
        )
        require(artifact_id.casefold() not in seen_ids, "duplicate public artifact ID")
        seen_ids.add(artifact_id.casefold())
        artifact_path = Path("artifacts") / f"{artifact_id}.json"
        require(not PureWindowsPath(artifact_id).is_reserved(), "invalid ID")
        expected_evidence.add(artifact_path)
        if item["artifact_type"] == "run":
            route_segments[Path("runs") / artifact_id] = "runs.$d$artifactId."
        elif item["artifact_type"] == "comparison":
            route = Path("comparisons") / artifact_id
            route_segments[route] = "comparisons.$d$artifactId."
            route_segments[route / "failures"] = "comparisons.$d$artifactId.failures."
        else:
            raise ValueError("unsupported public artifact type")

    require(
        public_files == {Path("evidence") / path for path in expected_evidence},
        "unexpected or missing file in apps/web/public",
    )
    output_files = files_under(out)
    require_matching_tree(evidence, out / "evidence", expected_evidence, "out/evidence")
    expected_output = next_route_files(route_segments)
    expected_output.update(Path("evidence") / path for path in expected_evidence)
    for source, destination, required_files in (
        (web / ".next/static", Path("_next/static"), set()),
        (web / "storybook-public-static", Path("storybook"), {Path("index.html"), index}),
    ):
        paths = files_under(source)
        require(
            bool(paths) and required_files <= paths, f"incomplete build input for {destination}"
        )
        require_matching_tree(source, out / destination, paths, f"out/{destination.as_posix()}")
        expected_output.update(destination / path for path in paths)
    require(output_files == expected_output, "unexpected or missing file in Pages route output")

    for path in sorted(expected_evidence):
        data = (out / "evidence" / path).read_bytes()
        print(f"{hashlib.sha256(data).hexdigest()}  evidence/{path.as_posix()}")
    counts = f"{len(expected_evidence)} evidence files; {len(output_files)} total files"
    print(f"PAGES_OUTPUT_OK: {counts}")


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        sys.exit(f"PAGES_OUTPUT_FAILED: could not read build files ({exc.strerror})")
    except (ValueError, KeyError, TypeError) as exc:
        sys.exit(f"PAGES_OUTPUT_FAILED: {exc}")
