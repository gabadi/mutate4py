"""CLI entry point for mutate4py."""

import argparse
import datetime
import sys

from mutate4py._discovery import discover_sites
from mutate4py._manifest import (
    build_manifest,
    embed_manifest,
    extract_manifest,
    manifests_structurally_equal,
    strip_manifest,
)

DEFAULT_WARNING_THRESHOLD = 1000


def scan_report(
    path: str, source: str, warning_threshold: int
) -> tuple[list[str], bool]:
    """Return (output_lines, exceeded_threshold) for a --scan run."""
    sites = discover_sites(source)
    total = len(sites)
    lines = [
        f"Mutation scan: {path}",
        f"Total mutation sites: {total}",
        f"Changed mutation sites: {total}",  # F1: no manifest, Changed == Total
        "Manifest exists: false",
    ]
    exceeded = total > warning_threshold
    if exceeded:
        lines.append(
            f"Warning: {total} mutation sites exceeds threshold {warning_threshold}."
        )
    return lines, exceeded


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mutate4py",
        description="Mutation testing for Python with an embedded-in-source manifest",
    )
    parser.add_argument("file", help="Python source file to analyse")
    parser.add_argument(
        "--scan", action="store_true", help="Count mutation sites; no test run"
    )
    parser.add_argument(
        "--mutation-warning",
        type=int,
        default=DEFAULT_WARNING_THRESHOLD,
        dest="warning_threshold",
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Embed or refresh the manifest footer in the source file; no test run",
    )

    args = parser.parse_args()

    try:
        with open(args.file) as f:
            source = f.read()
    except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.scan:
        lines, _ = scan_report(args.file, source, args.warning_threshold)
        print("\n".join(lines))
    elif args.update_manifest:
        _do_update_manifest(args.file, source)
    else:
        parser.print_help(file=sys.stderr)
        sys.exit(2)


def _do_update_manifest(path: str, source: str) -> None:
    existing, _ = extract_manifest(source)
    clean = strip_manifest(source)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate = build_manifest(clean, tested_at=tested_at)

    if existing is not None and manifests_structurally_equal(existing, candidate):
        print(f"Manifest unchanged: {path}")
        return

    embedded = embed_manifest(source, candidate)
    with open(path, "w") as f:
        f.write(embedded)
    print(f"Updated manifest: {path}")


if __name__ == "__main__":
    main()
