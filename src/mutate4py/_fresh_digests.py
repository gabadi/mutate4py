"""The fresh tests digest of every function in a measured source file (#105).

A scored run records these on the Manifest's function entries. The Measurement
supplies the reach; the rule for what a digest covers is in _tests_digest.
"""

import os

from mutate4py._discovery import discover_sites
from mutate4py._manifest import build_manifest
from mutate4py._measurement import Measurement, Static
from mutate4py._tests_digest import FunctionUnit, function_digest

__all__ = ["fresh_digests"]


def fresh_digests(measurement: Measurement, abs_source: str, clean_source: str) -> dict[str, str]:
    inputs = measurement.digest_inputs()
    path = os.path.realpath(abs_source)
    covered = measurement.covered_lines(abs_source)
    sites = discover_sites(clean_source)
    digests: dict[str, str] = {}
    for fn in build_manifest(clean_source, tested_at="")["functions"]:
        fid = fn["id"]
        site_lines = _reached_sites(sites, fid, covered)
        static_lines = _static_sites(measurement, abs_source, site_lines)
        digests[fid] = function_digest(inputs, FunctionUnit(path, fid), site_lines, static_lines)
    return digests


def _reached_sites(sites, fid: str, covered) -> frozenset[int]:
    """The lines of one function's Sites that the Measurement covered."""
    return frozenset(site.line for site in sites if site.function_id == fid and site.line in covered)


def _static_sites(measurement: Measurement, abs_source: str, site_lines: frozenset[int]) -> frozenset[int]:
    """The reached lines whose outcome is Static: the ones a Static Measurement settles."""
    return frozenset(line for line in site_lines if isinstance(measurement.outcome(abs_source, line), Static))
