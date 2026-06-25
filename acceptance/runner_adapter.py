#!/usr/bin/env python3
"""Persistent runner adapter for gherkin-mutator.

Reads newline-delimited JSON jobs from stdin; for each job runs the generated
acceptance entrypoint against the mutated feature JSON; writes JSON responses
to stdout.

Protocol (from APS mutator-spec.md):
  input:  {"id": "m1", "feature_json": "<path>", "generated_dir": "<dir>",
            "work_dir": "<dir>", "timeout": "30s"}
  output: {"id": "m1", "outcome": "test_failure|test_success|infrastructure_error",
            "output": "<text>", "error": "", "duration": <nanoseconds>}
"""
import json
import os
import re
import subprocess
import sys
import time


def _parse_timeout_ns(s: str) -> float:
    m = re.match(r"^(\d+(?:\.\d+)?)(s|ms|m)$", s or "30s")
    if not m:
        return 30.0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "ms":
        return val / 1000
    if unit == "m":
        return val * 60
    return val


def _run_job(job: dict) -> dict:
    job_id = job.get("id", "?")
    feature_json = job.get("feature_json", "")
    generated_dir = job.get("generated_dir", "")
    timeout_s = _parse_timeout_ns(job.get("timeout", "30s"))

    feature_stem = _stem_from_feature_json(feature_json)
    entrypoint = os.path.join(generated_dir, f"{feature_stem}_acceptance.py")

    if not os.path.isfile(entrypoint):
        return {
            "id": job_id,
            "outcome": "infrastructure_error",
            "output": "",
            "error": f"entrypoint not found: {entrypoint}",
            "duration": 0,
        }

    env = os.environ.copy()
    env["APS_FEATURE_JSON"] = feature_json

    start = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, entrypoint],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
        elapsed_ns = int((time.monotonic() - start) * 1_000_000_000)
        combined = result.stdout + result.stderr
        if result.returncode == 0:
            outcome = "test_success"
        else:
            outcome = "test_failure"
        return {
            "id": job_id,
            "outcome": outcome,
            "output": combined,
            "error": "",
            "duration": elapsed_ns,
        }
    except subprocess.TimeoutExpired:
        elapsed_ns = int((time.monotonic() - start) * 1_000_000_000)
        return {
            "id": job_id,
            "outcome": "infrastructure_error",
            "output": "",
            "error": f"timed out after {timeout_s}s",
            "duration": elapsed_ns,
        }
    except Exception as exc:
        elapsed_ns = int((time.monotonic() - start) * 1_000_000_000)
        return {
            "id": job_id,
            "outcome": "infrastructure_error",
            "output": "",
            "error": str(exc),
            "duration": elapsed_ns,
        }


def _stem_from_feature_json(feature_json: str) -> str:
    """Derive acceptance entrypoint stem from the mutated feature JSON path.

    Mutator places the JSON at: <work_dir>/mutations/<id>/feature.json
    The generated dir holds: <feature_stem>_acceptance.py
    We find the stem by reading the feature_path from the JSON IR.
    """
    try:
        with open(feature_json) as f:
            ir = json.load(f)
        feature_path = ir.get("feature_path", "")
        stem = os.path.basename(feature_path).replace(".feature", "")
        if stem:
            return stem
    except Exception:
        pass
    # fallback: walk up to find a stem from path components
    parts = os.path.normpath(feature_json).split(os.sep)
    return "complexity"


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except json.JSONDecodeError as e:
            print(json.dumps({"id": "?", "outcome": "infrastructure_error",
                               "output": "", "error": f"bad JSON: {e}", "duration": 0}),
                  flush=True)
            continue
        response = _run_job(job)
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
