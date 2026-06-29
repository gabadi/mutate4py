"""Low-level subprocess helper shared by serial and parallel mutation runners."""

import subprocess

__all__ = ["run_command"]


def run_command(cmd: str, cwd: str, timeout: float) -> tuple[str, bool]:
    """Run cmd via shell; return (status, timed_out) where status in {killed,timeout,survived}."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
        )
        return ("survived" if result.returncode == 0 else "killed", False)
    except subprocess.TimeoutExpired:
        return ("timeout", True)

# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-29T05:03:13Z","module_hash":"140b5a19257f812cf84093bca22817acc1b2a4edf5439cd51a49ee5a7137284b","functions":[{"id":"func/run_command","name":"run_command","line":8,"end_line":20,"hash":"d057ada7a6edbfaed83dc3883749643c727c691d1db3ac4ad44704c8754d4287"}]}
# mutate4py-manifest-end
