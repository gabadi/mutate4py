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

    feature_stem = _stem_from_feature_json(feature_json, generated_dir)
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


def _stem_from_feature_json(feature_json: str, generated_dir: str = "") -> str:
    """Derive acceptance entrypoint stem from the mutated feature JSON path.

    Mutator places the JSON at: <work_dir>/mutations/<id>/feature.json
    The generated dir holds: <feature_stem>_acceptance.py

    Strategy:
    1. Read feature_path from the JSON IR (present in parsed IR, absent in mutated JSONs).
    2. Read the feature name from the mutated JSON and match it against APS metadata
       entries to find the canonical feature_path → stem.
    """
    feature_name = None
    try:
        with open(feature_json) as f:
            ir = json.load(f)
        feature_path = ir.get("feature_path", "")
        stem = os.path.basename(feature_path).replace(".feature", "")
        if stem:
            return stem
        feature_name = ir.get("name", "")
    except Exception:
        pass

    # Mutated JSON has no feature_path — match by feature name against metadata.
    if generated_dir:
        metadata_dir = os.path.join(generated_dir, "metadata")
        if os.path.isdir(metadata_dir):
            for meta_file in sorted(os.listdir(metadata_dir)):
                if not meta_file.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(metadata_dir, meta_file)) as f:
                        meta = json.load(f)
                    fp = meta.get("feature_path", "")
                    stem = os.path.basename(fp).replace(".feature", "")
                    if not stem:
                        continue
                    # Match if feature name appears in the parsed IR for this stem.
                    ir_path = meta.get("ir_path", "")
                    if feature_name and ir_path and os.path.isfile(ir_path):
                        with open(ir_path) as f:
                            parsed = json.load(f)
                        if parsed.get("name", "") == feature_name:
                            return stem
                    elif stem and not feature_name:
                        return stem
                except Exception:
                    pass

    return "site-discovery"


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
