"""CLI dispatch and execution (issue #38 gate 11): turns resolved targets
into file reads, mode routing, and process exit codes.

Root resolution (positionals/globs, or uv workspace autodiscovery),
single-file vs. batch routing by arity, per-file mode dispatch (scan /
check-manifest / update-manifest / run-mutations), and the worst-code exit
aggregation across a batch all live here. Argument parsing and validation
stay in the CLI adapter (`__main__.py`) — this module never builds an
`argparse.ArgumentParser`, only reads the `argparse.Namespace` it's handed.

Like `_workspace.py`, this module exits the process directly (`sys.exit`)
rather than raising a typed error for the caller to translate: it is a
second adapter-tier module, not a domain module, so nothing needs to catch
its errors programmatically. The one exception is `NoFilesToProcessError`
raised by `_target_resolution`'s "no files kept" case, which the caller
(`main()`) still needs to catch to apply its own exit code — that contract
is unchanged by this module's existence.
"""

import argparse
import os
import sys

from mutate4py._runner import (
    CoverageError,
    CoverageSource,
    RunMutationsRequest,
    check_manifest,
    run_baseline,
    run_mutations,
    run_scan,
    update_manifest,
)
from mutate4py._target_resolution import (
    NoFilesToProcessError,
    _collect_py_files,
    _dedup_by_realpath,
    _expand_roots,
    _is_excluded,
)
from mutate4py._workspace import _discover_workspace_roots, _workspace_exclude_dirs


def _load_source(path: str) -> str:
    """Read source file; exit with error if unreadable."""
    try:
        with open(path) as f:
            return f.read()
    except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


def _syntax_error_reason(exc: SyntaxError) -> str:
    """Human-readable reason for a SyntaxError, independent of ast.parse's filename."""
    if exc.lineno is not None:
        return f"{exc.msg} (line {exc.lineno})"
    return exc.msg


def _report_parse_error(path: str, exc: SyntaxError) -> None:
    print(f"error: cannot parse {path}: {_syntax_error_reason(exc)}", file=sys.stderr)


def _parse_line_token(token: str) -> int:
    """Parse a single --lines token into a positive int; exit on error."""
    try:
        n = int(token)
    except ValueError:
        print(f"error: --lines value {token!r} is not a valid integer.", file=sys.stderr)
        sys.exit(2)
    if n < 1:
        print(
            f"error: --lines value {token!r} must be a positive integer (>= 1).",
            file=sys.stderr,
        )
        sys.exit(2)
    return n


def _parse_lines(lines_str: str | None) -> set[int] | None:
    """Parse --lines argument into a set of positive ints, or None if not given."""
    if lines_str is None:
        return None
    parts = [p.strip() for p in lines_str.split(",") if p.strip()]
    return {_parse_line_token(p) for p in parts}


def _run_scan(args: argparse.Namespace, path: str, source: str, cwd: str) -> None:
    """Execute --scan logic; exits with code 2 on CoverageError."""
    try:
        run_scan(
            path=path,
            source=source,
            warning_threshold=args.warning_threshold,
            coverage=CoverageSource(
                cov_cmd=args.cov_cmd,
                lcov_path=args.lcov,
                reuse_coverage=args.reuse_coverage,
                cwd=cwd,
            ),
        )
    except CoverageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


def _run_on_file(
    args: argparse.Namespace,
    py_file: str,
    source: str,
    cwd: str,
    baseline_duration: float | None = None,
) -> int:
    if args.check_manifest:
        return check_manifest(path=py_file, source=source, manifest_file=args.manifest_file)
    if args.update_manifest:
        update_manifest(path=py_file, source=source, manifest_file=args.manifest_file)
        return 0
    if args.scan:
        _run_scan(args, py_file, source, cwd)
        return 0
    lines_filter = _parse_lines(args.lines)
    max_workers = args.max_workers if args.max_workers is not None else 0
    return run_mutations(
        RunMutationsRequest(
            path=py_file,
            source=source,
            cov_cmd=args.cov_cmd,
            lcov_path=args.lcov,
            reuse_coverage=args.reuse_coverage,
            test_command=args.test_command,
            timeout_factor=args.timeout_factor,
            min_timeout=args.min_timeout,
            lines_filter=lines_filter,
            since_last_run=args.since_last_run,
            mutate_all=args.mutate_all,
            warning_threshold=args.warning_threshold,
            max_workers=max_workers,
            cwd=cwd,
            baseline_duration=baseline_duration,
            test_contexts_path=args.test_contexts,
            manifest_file=args.manifest_file,
            fork_server_requested=not args.no_fork_server,
        )
    )


def _needs_directory_baseline(files: list[str], args: argparse.Namespace) -> bool:
    """A shared baseline is only needed when the run will actually execute mutants."""
    return bool(files) and not (args.scan or args.update_manifest or args.check_manifest)


def _prepare_directory_baseline(args: argparse.Namespace, files: list[str], cwd: str) -> float:
    """Acquire coverage once and time the baseline for a directory run.

    Exits the process on failure, matching the single-file dispatch behavior.
    """
    from mutate4py._coverage import acquire_coverage

    try:
        acquire_coverage(
            cov_cmd=args.cov_cmd,
            lcov_path=args.lcov,
            reuse=args.reuse_coverage,
            cwd=cwd,
            source_path=os.path.abspath(files[0]),
        )
    except CoverageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    baseline_duration, baseline_error = run_baseline(args.test_command, cwd)
    if baseline_error is not None:
        print(f"baseline failed: {baseline_error}", file=sys.stderr)
        sys.exit(1)
    return baseline_duration


def _report_excluded(excluded: list[str]) -> None:
    """Print one line per file --exclude dropped from the walk (--verbose only)."""
    for path in excluded:
        print(f"Excluded: {path}")


def _collect_union_files(args: argparse.Namespace, roots: list[str]) -> list[str]:
    """The union's .py files across all roots: root order, deduped, raises
    NoFilesToProcessError if the whole union is empty (an individual empty
    root is silent, item 17)."""
    kept: list[str] = []
    excluded: list[str] = []
    for root in roots:
        result = _collect_py_files(root, args.exclude or (), args.prune_dirs)
        kept.extend(result.kept)
        excluded.extend(result.excluded)
    kept = _dedup_by_realpath(kept)
    if args.verbose:
        _report_excluded(excluded)
    if not kept:
        raise NoFilesToProcessError()
    return kept


def _run_files_and_exit(args: argparse.Namespace, files: list[str]) -> None:
    """Run the configured mode over every file; exit with the worst (highest)
    per-file code seen, so a selection disagreement (2) is never flattened into
    an ordinary failure (1). A failing file never stops the batch — including a
    file that fails to parse, which contributes code 2 and is tallied into the
    trailing parse-failure summary line."""
    cwd = os.getcwd()
    baseline_duration = None
    if _needs_directory_baseline(files, args):
        baseline_duration = _prepare_directory_baseline(args, files, cwd)
    exit_code = 0
    parse_failures = 0
    for py_file in files:
        try:
            exit_code = max(
                exit_code,
                _run_on_file(args, py_file, _load_source(py_file), cwd, baseline_duration),
            )
        except SyntaxError as exc:
            _report_parse_error(py_file, exc)
            exit_code = max(exit_code, 2)
            parse_failures += 1
    if parse_failures:
        print(f"error: {parse_failures} files could not be parsed", file=sys.stderr)
    sys.exit(exit_code)


def _dispatch_batch(args: argparse.Namespace, roots: list[str]) -> None:
    """One or more resolved roots: one shared baseline, and one exit code — the
    worst per-file code across the batch (item 2)."""
    _run_files_and_exit(args, _collect_union_files(args, roots))


def _raise_if_target_excluded(args: argparse.Namespace) -> None:
    """Raise NoFilesToProcessError when the single-file target itself
    matches an --exclude pattern."""
    if not _is_excluded(args.file, args.exclude or ()):
        return
    if args.verbose:
        print(f"Excluded: {args.file}")
    raise NoFilesToProcessError()


def _resolve_roots(args: argparse.Namespace) -> tuple[list[str], tuple[str, ...]]:
    """Positionals/globs, or uv workspace autodiscovery when none are given
    (issue #22 item 3). Autodiscovery also returns the real
    [tool.uv.workspace].exclude directories, so the shared collector skips
    them by path identity in every walk (item 10's second half) — not by
    re-encoding a literal directory path as a glob pattern, which a "*" in
    the directory's own name would misinterpret."""
    if args.files:
        return _expand_roots(args.files), ()
    return _discover_workspace_roots(), tuple(_workspace_exclude_dirs())


def _dispatch(args: argparse.Namespace) -> None:
    """Resolve positionals (or autodiscover a workspace), then route by
    arity (issue #22 item 2).

    A single resolved path that is a file runs the single-file path below,
    untouched; a single directory or two or more roots run as one batch.
    Routing a lone directory through _dispatch_batch (gate 11) means it now
    also gets _collect_union_files' realpath dedup, which a bare directory
    walk never applied on its own — a directory containing a symlinked .py
    file that aliases another file in the same walk now keeps only one of
    them, where both used to be kept. Narrow (requires an in-tree symlink
    alias) and arguably a correctness fix (multi-root batches already
    deduped this way), but it is a real deviation from ADR 0017's
    byte-for-byte framing, so it's called out here rather than silently.
    """
    roots, args.prune_dirs = _resolve_roots(args)
    if len(roots) > 1:
        _dispatch_batch(args, roots)
        return
    # Populates the args.file scratch field declared in _build_parser; the
    # single-file path below and _dispatch_batch's excluded-target check
    # both read it from here.
    args.file = roots[0]
    if os.path.isdir(args.file):
        _dispatch_batch(args, [args.file])
        return
    source = _load_source(args.file)  # a bad path must report itself, not "excluded"
    _raise_if_target_excluded(args)
    try:
        sys.exit(_run_on_file(args, args.file, source, os.getcwd()))
    except SyntaxError as exc:
        _report_parse_error(args.file, exc)
        sys.exit(2)
