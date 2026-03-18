#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
import time


SHUTDOWN_TIMEOUT_SECONDS = 3.0
child_process: subprocess.Popen[bytes] | None = None
received_signal: int | None = None


def terminate_child(signum: int, _frame: object) -> None:
    global received_signal
    received_signal = signum

    if child_process is None or child_process.poll() is not None:
        return

    try:
        os.killpg(child_process.pid, signum)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if child_process.poll() is not None:
            return
        time.sleep(0.1)

    try:
        os.killpg(child_process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def main() -> int:
    global child_process

    if len(sys.argv) < 2:
        print("usage: run_funkydns.py <command> [args...]", file=sys.stderr)
        return 2

    signal.signal(signal.SIGTERM, terminate_child)
    signal.signal(signal.SIGINT, terminate_child)

    child_process = subprocess.Popen(
        sys.argv[1:],
        start_new_session=True,
    )
    return_code = child_process.wait()

    if return_code < 0:
        return 128 + abs(return_code)
    if received_signal is not None:
        return 128 + received_signal
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
