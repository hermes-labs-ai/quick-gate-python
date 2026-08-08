from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from pygate.fs import now_iso
from pygate.models import CommandTrace

OUTPUT_TRUNCATION_MARKER = "\n[pygate: output truncated]\n"
DEFAULT_OUTPUT_CAP_BYTES = 1_048_576


def _argv_for(command: str | Sequence[str]) -> list[str]:
    if isinstance(command, str):
        # Shell syntax is intentionally data by default. Callers that require
        # shell compatibility must opt in with shell=True.
        return shlex.split(command)
    return [str(part) for part in command]


def _display_command(command: str | Sequence[str], argv: list[str], shell: bool) -> str:
    if isinstance(command, str) and shell:
        return command
    return shlex.join(argv)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:  # pragma: no cover - exercised on Windows CI
            process.terminate()
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=0.25)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:  # pragma: no cover - exercised on Windows CI
                process.kill()
        except ProcessLookupError:
            return


def _reader(pipe: object, limit: int, holder: dict[str, object]) -> None:
    # Popen pipes expose read() but typing the private file object precisely is
    # not useful here; the reader only needs the documented binary stream API.
    chunks: list[bytes] = []
    size = 0
    truncated = False
    while True:
        chunk = pipe.read(65536)  # type: ignore[attr-defined]
        if not chunk:
            break
        available = max(0, limit - size)
        if available:
            keep = chunk[:available]
            chunks.append(keep)
            size += len(keep)
        if len(chunk) > available:
            truncated = True
    holder["data"] = b"".join(chunks)
    holder["truncated"] = truncated


def _decode(data: object) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data or "")


def run_command(
    command: str | Sequence[str],
    *,
    cwd: Path | str | None = None,
    timeout_seconds: float | None = None,
    env: dict[str, str] | None = None,
    shell: bool = False,
    output_cap_bytes: int = DEFAULT_OUTPUT_CAP_BYTES,
) -> CommandTrace:
    """Run one command with argv-safe defaults and bounded process resources.

    String commands are tokenized with ``shlex``. Metacharacters therefore
    remain arguments unless the caller explicitly sets ``shell=True``.
    """

    if output_cap_bytes < 1:
        raise ValueError("output_cap_bytes must be positive")
    work_dir = str(cwd) if cwd else os.getcwd()
    merged_env = {**os.environ, **(env or {})}
    started_at = now_iso()
    start = time.monotonic()
    argv: list[str] = []
    display = command if isinstance(command, str) else ""
    timed_out = False
    missing_executable = False
    error: str | None = None
    diagnostics: list[str] = []
    stdout_holder: dict[str, object] = {}
    stderr_holder: dict[str, object] = {}
    process: subprocess.Popen[bytes] | None = None
    exit_code: int | None = None

    try:
        argv = _argv_for(command)
        display = _display_command(command, argv, shell)
        popen_command: str | list[str] = shlex.join(argv) if shell else argv
        if shell and isinstance(command, str):
            popen_command = command
        kwargs: dict[str, object] = {
            "shell": shell,
            "cwd": work_dir,
            "env": merged_env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
        elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):  # pragma: no cover
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(popen_command, **kwargs)  # type: ignore[arg-type]
        assert process.stdout is not None and process.stderr is not None
        stdout_thread = threading.Thread(target=_reader, args=(process.stdout, output_cap_bytes, stdout_holder))
        stderr_thread = threading.Thread(target=_reader, args=(process.stderr, output_cap_bytes, stderr_holder))
        stdout_thread.start()
        stderr_thread.start()
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            diagnostics.append("process group terminated after command deadline")
            _terminate_process_group(process)
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        exit_code = process.returncode
    except ValueError as exc:
        exit_code = 2
        error = str(exc)
        diagnostics.append("invalid command arguments")
    except FileNotFoundError as exc:
        missing_executable = True
        exit_code = 127
        error = str(exc)
        diagnostics.append("executable not found")
    except OSError as exc:
        exit_code = 1
        error = str(exc)
        diagnostics.append("could not start process")
    finally:
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

    stdout = _decode(stdout_holder.get("data"))
    stderr = _decode(stderr_holder.get("data"))
    stdout_truncated = bool(stdout_holder.get("truncated", False))
    stderr_truncated = bool(stderr_holder.get("truncated", False))
    output_truncated = stdout_truncated or stderr_truncated
    if stdout_truncated:
        stdout += OUTPUT_TRUNCATION_MARKER
    if stderr_truncated:
        stderr += OUTPUT_TRUNCATION_MARKER

    process_signal = -exit_code if exit_code is not None and exit_code < 0 else None
    if process_signal is not None:
        diagnostics.append(f"process terminated by signal {process_signal}")
    if timed_out:
        exit_code = 1

    return CommandTrace(
        command=display,
        cwd=work_dir,
        started_at=started_at,
        duration_ms=int((time.monotonic() - start) * 1000),
        exit_code=exit_code,
        timed_out=timed_out,
        stdout=stdout,
        stderr=stderr,
        argv=argv,
        shell=shell,
        timeout_seconds=timeout_seconds,
        output_truncated=output_truncated,
        signal=process_signal,
        missing_executable=missing_executable,
        error=error,
        diagnostics=diagnostics,
    )
