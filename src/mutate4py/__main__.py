"""CLI entry point for mutate4py."""

import argparse
import sys

from mutate4py._discovery import discover_sites

DEFAULT_WARNING_THRESHOLD = 1000


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

    args = parser.parse_args()

    try:
        source = open(args.file).read()
    except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.scan:
        sites = discover_sites(source)
        total = len(sites)
        changed = total  # F1: no manifest, Changed == Total

        print(f"Mutation scan: {args.file}")
        print(f"Total mutation sites: {total}")
        print(f"Changed mutation sites: {changed}")
        print("Manifest exists: false")

        if total > args.warning_threshold:
            print(
                f"Warning: {total} mutation sites exceeds threshold {args.warning_threshold}."
            )
    else:
        parser.print_help(file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
