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
# {"version":1,"tested_at":"2026-06-29T00:53:58Z","module_hash":"d47fa9395330a6e5d4856064ab24026a4a8f726aee20c4112ef5c309f756e10a","functions":[{"id":"func/run_command","name":"run_command","line":8,"end_line":20,"hash":"8e2a378d52be448deba0fb8acbe590d7eeae3aa9aac535fcb0386587d718dd7f"}]}
# mutate4py-manifest-end
