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
# {"version":1,"tested_at":"2026-06-29T00:35:57Z","module_hash":"444695f33b6022fef260652cc481a6349b6cf5f4c68e7c947b1a030bffd85986","functions":[{"id":"func/run_command","name":"run_command","line":8,"end_line":20,"hash":"e0326625f70f06f703620b38a6f8d084ddd1d5680d22ae678c1c64e9fe03aa8a"}]}
# mutate4py-manifest-end
