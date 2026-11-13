"""Shared argument builder for the dispatch-cluster unit tests."""

import argparse


def make_args(**kwargs):
    """Build a minimal argparse.Namespace for dispatch-cluster tests."""
    defaults = dict(
        scan=False,
        update_manifest=False,
        check_manifest=False,
        lines=None,
        since_last_run=False,
        mutate_all=False,
        max_workers=None,
        timeout_factor=10,
        min_timeout=1.0,
        pytest_args=[],
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
        warning_threshold=50,
        manifest_file=False,
        verbose=False,
        exclude=None,
        prune_dirs=(),
        no_fork=False,
        allow_survivors=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)
