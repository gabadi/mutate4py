"""CLI entry point for mutate4py."""

import argparse
import datetime
import os
import sys

from mutate4py._coverage import CoverageError, acquire_coverage, partition_sites
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


def scan_report_with_coverage(
    path: str,
    source: str,
    warning_threshold: int,
    *,
    cov_cmd: str | None,
    lcov_path: str | None,
    reuse_coverage: bool,
    cwd: str,
) -> tuple[list[str], bool]:
    """Return (output_lines, exceeded_threshold) for a --scan run with coverage."""
    sites = discover_sites(source)
    total = len(sites)

    covered_lines = acquire_coverage(
        cov_cmd=cov_cmd,
        lcov_path=lcov_path,
        reuse=reuse_coverage,
        cwd=cwd,
        source_path=os.path.abspath(path),
    )
    covered, uncovered = partition_sites(sites, covered_lines)

    lines = [
        f"Mutation scan: {path}",
        f"Total mutation sites: {total}",
        f"Covered mutation sites: {covered}",
        f"Uncovered mutation sites: {uncovered}",
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
    parser.add_argument("--cov-cmd", dest="cov_cmd", default=None,
                        help="Shell command to run once to generate LCOV coverage")
    parser.add_argument("--lcov", dest="lcov", default=None,
                        help="Path to a pre-generated LCOV file")
    parser.add_argument("--reuse-coverage", action="store_true", dest="reuse_coverage",
                        help="Read LCOV from coverage.lcov (default path)")

    args = parser.parse_args()

    # Check pairwise exclusivity of coverage flags (ADR 0008)
    cov_flags = [args.cov_cmd is not None, args.lcov is not None, args.reuse_coverage]
    if sum(cov_flags) > 1:
        print(
            "error: --cov-cmd, --lcov, and --reuse-coverage are mutually exclusive; "
            "supply at most one.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        with open(args.file) as f:
            source = f.read()
    except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.scan:
        has_coverage = args.cov_cmd is not None or args.lcov is not None or args.reuse_coverage
        if has_coverage:
            try:
                lines, _ = scan_report_with_coverage(
                    args.file,
                    source,
                    args.warning_threshold,
                    cov_cmd=args.cov_cmd,
                    lcov_path=args.lcov,
                    reuse_coverage=args.reuse_coverage,
                    cwd=os.getcwd(),
                )
            except CoverageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                sys.exit(2)
        else:
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
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
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
